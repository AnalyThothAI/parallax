# Verification — Macro Decision Console

**Status**: In progress
**Superseded by**: Not superseded
**Date**: 2026-06-16
**Owning spec**: `docs/sdd/features/active/2026-06-16-macro-decision-console/spec.md`
**Owning plan**: `docs/sdd/features/active/2026-06-16-macro-decision-console/plan.md`
**Branch**: `codex/macro-decision-console`
**Worktree**: `.worktrees/macro-decision-console`
**Approved by**: Delegated goal from user on 2026-06-16
**Approved at**: 2026-06-16
**Diff**: Hard-deletion slice, timsun-style decision-console reading order, and
macrodata source-health diagnostics implemented; source backlog and final
retained-route QA remain open.

## Discovery Evidence

Recorded during planning on 2026-06-16:

- `uv run parallax config` exited 0. Redacted summary: config path `/Users/qinghuan/.parallax/config.yaml`; workers config path `/Users/qinghuan/.parallax/workers.yaml`; macrodata enabled; FRED configured through env name `FINANCE_FRED_API_KEY`; no secret values printed.
- `uv run parallax macro status` exited 0. Summary: migration ready, macrodata package version `0.1.8`, required series count 128, missing required series count 0, observations count 63,407, concept count 128, latest snapshot status `partial`, history coverage ratio 0.8425, projection lag 0 days, 20 concepts below minimum history.
- `uv run macrodata doctor` in `/Users/qinghuan/Documents/code/macrodata-cli` exited 0. Summary: standalone checkout version `0.1.8`, `fred_api_key_configured=false`.
- `uv run macrodata bundle macro-core --asof 2026-06-16` in `/Users/qinghuan/Documents/code/macrodata-cli` exited 0 with `data_quality=partial`, requested 128 series, available 67 series, source chain `nyfed`, `treasury_fiscal`, `fred`, `yahoo`, `cftc`, and FRED public fallback errors dominated by `provider_timeout`.
- FRED/Federal Reserve source research on 2026-06-16 confirmed SLOOS as a public credit source. Federal Reserve says SLOOS covers changes in bank lending standards/terms and loan demand. FRED release `Senior Loan Officer Opinion Survey on Bank Lending Practices` exposes SLOOS series including `DRTSCILM`, `DRTSCIS`, `DRSDCILM`, and `DRSDCIS`.
- FRED/Federal Reserve source research on 2026-06-16 confirmed loan-quality public credit sources. Federal Reserve `Charge-Off and Delinquency Rates on Loans and Leases at Commercial Banks` defines delinquent loans/leases and charge-off rates; FRED exposes `DRBLACBS`, `DRCLACBS`, `CORBLACBS`, and `CORCACBS`.
- Cboe/FRED/ProShares/Yahoo source research on 2026-06-16 and 2026-06-17 confirmed that FRED provides public VIX/VIX3M index series, Cboe public historical downloads provide VIX1D/VIX9D/VVIX/SKEW, ProShares VIXM is a public mid-term VIX futures ETF proxy, and Yahoo exposes `^MOVE` as a daily rates-volatility proxy. This feature adds `yahoo:VIXM`, `yahoo:^MOVE`, `cboe:VIX1D`, `cboe:VIX9D`, `cboe:VVIX`, and `cboe:SKEW` as evidence for `volatility/vix`; the real CFE VIX futures curve and licensed ICE/Bloomberg MOVE distribution remain source gaps.
- FRED/BLS source research on 2026-06-16 confirmed that `JTSJOL` provides monthly total nonfarm job openings and `CES0500000003` provides monthly private-sector average hourly earnings. This feature wires JOLTS into `economy/employment`, adds average hourly earnings, and removes the stale JOLTS/hourly-earnings gap labels.
- BLS source research on 2026-06-16 confirmed that the official CPI, Employment Situation, and PPI schedule pages expose parsable release-date rows with reference period, release date, and release time. Task 34 wires those official pages into macrodata-cli `macro-calendar-core`; actual-vs-consensus, revisions, and surprise history remain source gaps.
- Existing macrodata coverage already included `PCE`, `PCEC96`, `PSAVERT`, and `UMCSENT`. This feature folds those consumer facts into `economy/gdp` after deleting `economy/consumer`, so consumption evidence remains visible without restoring a separate weak route.
- Existing macrodata coverage already included FRED/Cboe cross-asset volatility indexes and FRED credit rating-ladder/financial-condition indexes. This feature folds those facts into retained `volatility/vix` and `credit/stress` pages instead of restoring the deleted volatility dashboard or CDS/dealer pages.
- Existing macrodata coverage already included 5Y/10Y/30Y TIPS real rates, 5Y/10Y/5Y5Y breakevens, GDP deflator, PCE/core PCE, and MICH expectations. This feature folds those facts into retained `rates/real-rates` and `economy/inflation` pages instead of leaving them stranded in the backend concept set.
- Existing macrodata coverage already included public equity, bond, commodity, FX, growth breadth, daily effective fed funds, and CFTC positioning concepts. This feature folds the remaining implemented macro-core concepts into retained pages so the module catalog no longer strands implemented concepts outside the product surface.

## Spec compliance

| Acceptance criterion                                                                                                                             | Status      | Evidence                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          |
| ------------------------------------------------------------------------------------------------------------------------------------------------ | ----------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| AC1 - WHEN a user hard-loads `/macro` THEN the system SHALL show the decision console.                                                           | pass        | Scenario emits decision fields; overview renders "今日决策台" in the order 3 个最重要变化, 确认 / 背离, 流动性压力, 未来 24/72h 催化剂, 交易映射, 昨日判断复盘, 未来 2 周情景, Watchlist 与触发提醒, 数据可信度层, with raw codes hidden. The overview now renders backend `structured_analysis` as `跨域判断链` immediately after the decision console, then sibling `market_event_flow` as `市场事件流` before the market board; the decision console no longer includes `event_catalysts` or `event_heatmap`. `structured_analysis` begins with a scenario-derived `市场主线` row and adds source-backed `美联储沟通` from official Fed text events before domain diagnostics; the row set is not hard-truncated, so fully populated snapshots keep assets, rates, policy, liquidity, growth, employment, inflation, volatility, and credit together. `top_changes` now falls back to source-backed feature deltas such as DXY, 10Y, and HY OAS when trigger rules are quiet, and those rows carry structured change/latest/source/as-of/severity evidence. Trade Map entries now include deterministic asset legs and holding-period review evidence. Watch triggers carry 24h/72h horizon and priority labels for the short-window catalyst strip, while `watchlist_alerts` replaces the old generic watch/invalidations section with Trade Map assets plus scenario watch, invalidation, and quality rules. |
| AC2 - WHEN a user opens macro navigation THEN the system SHALL show only source-backed primary routes.                                           | pass        | Macro catalog, frontend registry, navigation tree, route tests, and sidebar tests remove proxy/gap-only pages, including the rate-expectations proxy page, duplicate bank-reserves liquidity page, generic liquidity-transmission page, and generic public-operations liquidity page.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             |
| AC3 - WHEN a deleted macro route is opened directly THEN the system SHALL use ordinary not-found behavior.                                       | pass        | Deleted ids are absent from catalog/route registry and now route to the ordinary `404 Not Found` route-error surface; frontend `unsupported` product-tier/types, macro unsupported panel, and CSS branch were removed rather than hidden.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| AC4 - WHEN FRED public CSV is unavailable or timed out THEN macrodata-cli SHALL return clear diagnostics.                                        | pass        | `macrodata-cli` bundle snapshots now expose `source_health`; FRED public CSV timeout tests assert `access_mode=public_csv`, provider status, missing counts, error codes, and retryability.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       |
| AC5 - WHEN Parallax runtime has FRED configured THEN macro status SHALL report redacted configured state.                                        | pass        | Discovery confirms current redacted reporting.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| AC6 - WHEN implementation is verified THEN all listed gates SHALL pass or list a baseline blocker.                                               | in progress | Hard-deletion verification passed; full feature gates remain open.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| AC7 - WHEN official event bundles are imported THEN Parallax SHALL keep them outside numeric macro-core scoring and render source-backed events. | pass        | Live `macro-calendar-core` and `treasury-auction-core` syncs imported event observations; `fed-text-core` live macrodata smoke/fetch/history checks return official Federal Reserve documents; current-code overview module payload renders Fed/BEA/BLS calendar, Treasury auction calendar/result, and Fed text events from `event:*` rows in sibling `module_read.market_event_flow` with source URLs and metadata while `MACRO_CORE_CONCEPTS` stays numeric-only.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| AC8 - WHEN macro_sync enqueues due work THEN it SHALL schedule every configured bundle and report stale macrodata packages.                      | pass        | Unit tests cover multi-bundle scheduling for `macro-core`, `macro-calendar-core`, `treasury-auction-core`, `fed-text-core`, and `crypto-derivatives-core`, plus stale-package/missing-bundle diagnostics. Parallax is now pinned to macrodata-cli `0.1.22` / `dd86aa8bcd234e8fb427ba9d058e9b478e2a0e6c`; runtime state reports all five configured bundles and all required bundle series available.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |

Deviations from spec:

- None recorded.

Deviations from plan:

- None recorded.

## Verification commands

Hard-deletion slice evidence:

```text
$ uv run pytest tests/architecture/test_macro_no_compatibility_contract.py -q
13 passed
exit code: 0

$ uv run pytest tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py tests/architecture/test_macro_no_compatibility_contract.py -q
98 passed
exit code: 0

$ cd web && npm run test -- tests/unit/features/macro/model/macroPageRegistry.test.ts tests/unit/features/macro/model/macroRoutes.test.ts tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts tests/unit/features/macro/model/macroTableColumns.test.ts tests/component/features/macro/MacroRatesWorkbench.test.tsx tests/component/features/cockpit/ui/AppSidebar.test.tsx tests/component/features/macro/MacroShell.test.tsx tests/component/features/macro/MacroDataTable.test.tsx tests/routes/macro.route.test.tsx --run
9 files passed, 60 tests passed
exit code: 0

$ cd web && npm run typecheck
exit code: 0

$ cd web && npm run lint
ESLint passed; architecture tests 13 files passed, 73 tests passed
exit code: 0

$ cd web && npm run test -- tests/unit/features/macro/model/macroRoutes.test.ts tests/unit/features/macro/model/macroPageRegistry.test.ts tests/routes/macro.route.test.tsx --run && npm run typecheck && npm run lint && npm run test:e2e -- tests/e2e/golden-paths/macro-terminal.spec.ts --project=desktop-1366 -g "hard-deleted routes"
Test files passed: 3 Vitest route/model files; 13 architecture files; 1 Playwright desktop route-error check.
Tests passed: 16 Vitest route/model tests; 73 architecture tests; 1 Playwright test.
exit code: 0

$ uv run pytest tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py -q && cd web && npm run test -- tests/routes/macro.route.test.tsx tests/component/features/cockpit/ui/AppSidebar.test.tsx tests/component/features/macro/MacroModulePages.test.tsx tests/component/features/macro/MacroRatesWorkbench.test.tsx tests/unit/features/macro/model/macroRoutes.test.ts tests/unit/features/macro/model/macroPageRegistry.test.ts tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts --run && npm run typecheck && npm run lint && npm run test:e2e -- tests/e2e/golden-paths/macro-terminal.spec.ts --project=desktop-1366 -g "hard-deleted routes"
Python macro module/API tests: 120 passed.
Vitest macro route/component/model tests: 7 files passed, 54 tests passed.
Frontend typecheck passed.
Frontend lint passed: ESLint plus 13 architecture files, 73 architecture tests.
Playwright hard-deleted routes: 1 desktop test passed.
exit code: 0

$ cd web && npm run test -- ../web/tests/unit/features/macro/model/macroRoutes.test.ts ../web/tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts --run
2 files passed, 10 tests passed.
exit code: 0

$ uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py -q && uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py
92 passed.
Ruff checks passed.
exit code: 0

$ uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py -q && uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py
93 passed.
Ruff checks passed.
exit code: 0

$ uv run pytest tests/unit/domains/macro_intel/test_macro_module_catalog.py::test_catalog_exposes_exact_supported_module_ids tests/unit/domains/macro_intel/test_macro_module_catalog.py::test_catalog_hard_deletes_proxy_only_modules tests/unit/domains/macro_intel/test_macro_module_catalog.py::test_rrp_tga_page_absorbs_public_market_operations_evidence -q
3 passed.
exit code: 0

$ cd web && npm run test -- tests/unit/features/macro/model/macroRoutes.test.ts tests/unit/features/macro/model/macroPageRegistry.test.ts --run
2 files passed, 7 tests passed.
exit code: 0

$ uv run pytest tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py tests/architecture/test_macro_no_compatibility_contract.py -q
137 passed.
exit code: 0

$ cd web && npm run test -- tests/routes/macro.route.test.tsx tests/component/features/cockpit/ui/AppSidebar.test.tsx tests/component/features/macro/MacroModulePages.test.tsx tests/component/features/macro/MacroRatesWorkbench.test.tsx tests/unit/features/macro/model/macroRoutes.test.ts tests/unit/features/macro/model/macroPageRegistry.test.ts tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts --run
7 files passed, 54 tests passed.
exit code: 0

$ cd web && npm run typecheck
exit code: 0

$ cd web && npm run lint
ESLint passed; architecture tests 13 files passed, 73 tests passed.
exit code: 0

$ cd web && npm run test:e2e -- tests/e2e/golden-paths/macro-terminal.spec.ts --project=desktop-1366 -g "hard-deleted routes"
1 Playwright desktop route-error test passed.
exit code: 0

$ uv run ruff check src/parallax/domains/macro_intel/services/macro_module_catalog.py src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_catalog.py
Ruff checks passed.
exit code: 0

$ uv run parallax config
Redacted summary: config path `/Users/qinghuan/.parallax/config.yaml`; workers config path `/Users/qinghuan/.parallax/workers.yaml`; macrodata enabled; FRED configured.
exit code: 0

$ uv run parallax macro status
Summary: macrodata-cli `0.1.14`; required bundle count 4; required bundle series available; observations 81,571; concepts 161; latest snapshot `ready`; facts max observed at `2026-06-16`; projection lag 0.
exit code: 0

$ uv run python <live macro module audit>
Summary: config path `/Users/qinghuan/.parallax/config.yaml`; workers config path `/Users/qinghuan/.parallax/workers.yaml`; module count 16; `liquidity/reserves`, `liquidity/transmission-chain`, `liquidity/operations`, and `liquidity/fed-balance-sheet` deleted from the catalog; `liquidity/rrp-tga` absorbs Fed assets, reserve balances, NY Fed RRP, and SRF evidence; snapshot `ready`; facts max observed at `2026-06-16`; projection lag 0; retained modules report no missing backend module.
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py && uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py
SDD artifact validation passed.
exit code: 0

$ cd web && node --input-type=module <playwright macro smoke>
result: `/macro` rendered with no deleted route labels in sampled navigation;
direct `/macro/assets/crypto-derivatives` rendered the route-error surface;
console/pageerror issue count 0.
exit code: 0

$ uv run pytest tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/domains/macro_intel/test_macro_scenario_engine.py tests/unit/domains/macro_intel/test_macro_regime_engine.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py tests/architecture/test_macro_no_compatibility_contract.py -q
105 passed
exit code: 0

$ cd web && npm run test -- tests/unit/features/macro/model/macroPageRegistry.test.ts tests/unit/features/macro/model/macroRoutes.test.ts tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts tests/unit/features/macro/model/macroTableColumns.test.ts tests/component/features/macro/MacroRatesWorkbench.test.tsx tests/component/features/cockpit/ui/AppSidebar.test.tsx tests/component/features/macro/MacroShell.test.tsx tests/component/features/macro/MacroDataTable.test.tsx tests/component/features/macro/MacroModulePages.test.tsx tests/routes/macro.route.test.tsx --run
10 files passed, 66 tests passed
exit code: 0

$ cd web && npm run lint
ESLint passed; architecture tests 13 files passed, 73 tests passed
exit code: 0

$ cd web && npm run typecheck
exit code: 0

$ cd web && node --input-type=module <playwright mocked macro decision-console smoke>
result: desktop and mobile `/macro` rendered "今日决策台"; localized labels were visible; raw codes `risk_down_credit_sensitive` and `missing_asset_spy` were absent.
exit code: 0

$ cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest tests/unit/test_bundles.py::test_rates_core_bundle_exposes_missing_api_key_diagnostics tests/unit/test_bundles.py::test_rates_core_bundle_marks_all_series_missing_unavailable tests/cli/test_bundle_commands.py::test_rates_core_without_fred_api_key_uses_public_csv tests/cli/test_bundle_commands.py::test_rates_core_all_series_failing_is_unavailable -q
4 passed
exit code: 0

$ cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest tests/unit/test_bundles.py tests/provider/test_fred_provider.py tests/cli/test_bundle_commands.py -q
28 passed
exit code: 0

$ cd /Users/qinghuan/Documents/code/macrodata-cli && uv run ruff check .
All checks passed
exit code: 0

$ cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest -q
105 passed
exit code: 0

$ cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest tests/unit/test_catalog.py::test_catalog_contains_sloos_credit_supply_and_demand_series tests/unit/test_bundles.py::test_bundle_constants_include_supported_core_series -q
2 passed
exit code: 0

$ cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest tests/unit/test_catalog.py tests/unit/test_bundles.py tests/cli/test_bundle_commands.py -q
34 passed
exit code: 0

$ uv run pytest tests/unit/domains/macro_intel/test_macro_migration_contract.py::test_macro_constants_map_sloos_credit_supply_and_demand_concepts tests/unit/domains/macro_intel/test_macro_module_catalog.py::test_credit_stress_page_includes_sloos_supply_and_demand_evidence -q
2 passed
exit code: 0

$ uv run pytest tests/unit/domains/macro_intel/test_macro_migration_contract.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_cli_macro_commands.py -q
95 passed
exit code: 0

$ cd /Users/qinghuan/Documents/code/macrodata-cli && uv run ruff check .
All checks passed
exit code: 0

$ uv run pytest tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/domains/macro_intel/test_macro_migration_contract.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_cli_macro_commands.py tests/unit/test_api_macro_contract.py -q
131 passed
exit code: 0

$ cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest tests/unit/test_catalog.py::test_catalog_contains_loan_quality_credit_series tests/unit/test_bundles.py::test_bundle_constants_include_supported_core_series -q
2 passed
exit code: 0

$ uv run pytest tests/unit/domains/macro_intel/test_macro_migration_contract.py::test_macro_constants_map_loan_quality_credit_concepts tests/unit/domains/macro_intel/test_macro_module_catalog.py::test_credit_stress_page_includes_loan_quality_evidence -q
2 passed
exit code: 0

$ cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest tests/unit/test_catalog.py tests/unit/test_bundles.py tests/cli/test_bundle_commands.py -q
35 passed
exit code: 0

$ uv run pytest tests/unit/domains/macro_intel/test_macro_migration_contract.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_cli_macro_commands.py tests/unit/test_api_macro_contract.py -q
133 passed
exit code: 0

$ cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest -q
106 passed
exit code: 0

$ cd /Users/qinghuan/Documents/code/macrodata-cli && uv run ruff check .
All checks passed
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py && uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest tests/unit/test_catalog.py tests/unit/test_bundles.py -q
red run before implementation: 2 failed, 26 passed
failures: missing `yahoo:VIXM` catalog entry and volatility-core size still 8.
exit code: 1

$ uv run pytest tests/unit/domains/macro_intel/test_macro_migration_contract.py tests/unit/domains/macro_intel/test_macro_module_catalog.py -q
red run before implementation: 2 failed, 26 passed
failures: missing `yahoo:VIXM` provider mapping and missing `asset:vixm` in `volatility/vix`.
exit code: 1

$ cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest tests/unit/test_catalog.py tests/unit/test_bundles.py -q
28 passed
exit code: 0

$ uv run pytest tests/unit/domains/macro_intel/test_macro_migration_contract.py tests/unit/domains/macro_intel/test_macro_module_catalog.py -q
28 passed
exit code: 0

$ cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest -q
106 passed
exit code: 0

$ cd /Users/qinghuan/Documents/code/macrodata-cli && uv run ruff check .
All checks passed
exit code: 0

$ uv run pytest tests/unit/domains/macro_intel/test_macro_migration_contract.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_cli_macro_commands.py tests/unit/test_api_macro_contract.py -q
135 passed
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py && uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py
exit code: 1
remaining failures are unchanged active-touch conflicts and one uncited-background
issue in `2026-06-12-kappa-cqrs-governance-root-fix`.

$ cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest tests/unit/test_catalog.py tests/unit/test_bundles.py -q
red run before implementation: 3 failed, 26 passed
failures: missing `fred:CES0500000003` catalog entry and economy-core size still 20.
exit code: 1

$ uv run pytest tests/unit/domains/macro_intel/test_macro_migration_contract.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/domains/macro_intel/test_macro_module_views.py::test_gap_payloads_do_not_preserve_labels_for_implemented_source_gaps -q
red run before implementation: 3 failed, 28 passed
failures: missing average-hourly-earnings concept mapping, missing JOLTS/hourly-earnings employment-page evidence, and stale implemented-source gap labels.
exit code: 1

$ cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest tests/unit/test_catalog.py tests/unit/test_bundles.py -q
29 passed
exit code: 0

$ uv run pytest tests/unit/domains/macro_intel/test_macro_migration_contract.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/domains/macro_intel/test_macro_module_views.py::test_gap_payloads_do_not_preserve_labels_for_implemented_source_gaps -q
31 passed
exit code: 0

$ cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest -q
109 passed
exit code: 0

$ cd /Users/qinghuan/Documents/code/macrodata-cli && uv run ruff check .
All checks passed
exit code: 0

$ uv run pytest tests/unit/domains/macro_intel/test_macro_migration_contract.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_cli_macro_commands.py tests/unit/test_api_macro_contract.py -q
138 passed
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py && uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py
exit code: 1
remaining failures are unchanged active-touch conflicts and one uncited-background
issue in `2026-06-12-kappa-cqrs-governance-root-fix`.

$ cd web && npm run lint
ESLint passed; architecture tests 13 files passed, 73 tests passed
exit code: 0

$ cd web && npm run typecheck
exit code: 0

$ cd web && npm run test -- tests/unit/features/macro/model/macroPageRegistry.test.ts tests/unit/features/macro/model/macroRoutes.test.ts tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts tests/unit/features/macro/model/macroTableColumns.test.ts tests/component/features/macro/MacroRatesWorkbench.test.tsx tests/component/features/cockpit/ui/AppSidebar.test.tsx tests/component/features/macro/MacroShell.test.tsx tests/component/features/macro/MacroDataTable.test.tsx tests/component/features/macro/MacroModulePages.test.tsx --run
9 files passed, 57 tests passed
exit code: 0

$ cd web && npm run test:e2e -- tests/e2e/golden-paths/macro-responsive-audit.spec.ts --project=desktop-1366
1 passed
exit code: 0

$ cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx -t "renders overview page grammar" --run
red run before implementation: 1 failed
failure: `今日决策台` rendered only 重要变化 / 交易映射 / 数据可信度 and did
not expose 确认 / 背离 or 观察触发 / 失效条件.
exit code: 1

$ cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx -t "renders overview page grammar" --run
1 passed
exit code: 0

$ cd web && npm run test -- tests/unit/features/macro/model/macroPageRegistry.test.ts tests/unit/features/macro/model/macroRoutes.test.ts tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts tests/unit/features/macro/model/macroTableColumns.test.ts tests/component/features/macro/MacroRatesWorkbench.test.tsx tests/component/features/cockpit/ui/AppSidebar.test.tsx tests/component/features/macro/MacroShell.test.tsx tests/component/features/macro/MacroDataTable.test.tsx tests/component/features/macro/MacroModulePages.test.tsx --run
9 files passed, 57 tests passed
exit code: 0

$ cd web && npm run typecheck
exit code: 0

$ cd web && npm run lint
ESLint passed; architecture tests 13 files passed, 73 tests passed
exit code: 0

$ cd web && npm run test:e2e -- tests/e2e/golden-paths/macro-responsive-audit.spec.ts --project=desktop-1366
1 passed
exit code: 0

$ Playwright/Chrome MCP local smoke at http://127.0.0.1:5173/macro
result: attempted after starting Vite; Playwright MCP browser was killed during
launch and Chrome DevTools MCP timed out creating the page. This is recorded as
tooling failure, not app verification. Mocked Playwright e2e above remains the
browser evidence for this UI change.
exit code: not available

$ uv run pytest tests/unit/domains/macro_intel/test_macro_scenario_engine.py::test_build_macro_scenario_derives_top_changes_from_feature_deltas_without_triggers -q
red run before implementation: 1 failed
failure: `scenario["top_changes"]` was empty when triggers were empty even
though DXY, 10Y, HY OAS, and SPX had current feature deltas.
exit code: 1

$ uv run pytest tests/unit/domains/macro_intel/test_macro_scenario_engine.py::test_build_macro_scenario_derives_top_changes_from_feature_deltas_without_triggers -q
1 passed
exit code: 0

$ uv run ruff check src/parallax/domains/macro_intel/services/macro_scenario_engine.py tests/unit/domains/macro_intel/test_macro_scenario_engine.py
All checks passed
exit code: 0

$ uv run pytest tests/unit/domains/macro_intel/test_macro_scenario_engine.py tests/unit/domains/macro_intel/test_macro_regime_engine.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py -q
82 passed
exit code: 0

$ uv run pytest tests/unit/domains/macro_intel/test_macro_migration_contract.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_cli_macro_commands.py tests/unit/test_api_macro_contract.py -q
150 passed
exit code: 0

$ cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx -t "renders overview page grammar" --run
red run before implementation: 1 failed
failure: Trade Map showed `确认：待确认信号 / HY OAS 5日走阔` for the known
`sofr_above_iorb` confirm code.
exit code: 1

$ cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx -t "renders overview page grammar" --run
1 passed
exit code: 0

$ cd web && npm run test -- tests/unit/features/macro/model/macroPageRegistry.test.ts tests/unit/features/macro/model/macroRoutes.test.ts tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts tests/unit/features/macro/model/macroTableColumns.test.ts tests/component/features/macro/MacroRatesWorkbench.test.tsx tests/component/features/cockpit/ui/AppSidebar.test.tsx tests/component/features/macro/MacroShell.test.tsx tests/component/features/macro/MacroDataTable.test.tsx tests/component/features/macro/MacroModulePages.test.tsx --run
9 files passed, 57 tests passed
exit code: 0

$ cd web && npm run typecheck
exit code: 0

$ cd web && npm run lint
ESLint passed; architecture tests 13 files passed, 73 tests passed
exit code: 0

$ uv run pytest tests/unit/domains/macro_intel/test_macro_scenario_engine.py::test_build_macro_scenario_emits_funding_stress_trade_map -q
red run before implementation: 1 failed
failure: `scenario["trade_map"][0]` had no `legs` for asset-level Trade Map actions.
exit code: 1

$ cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx -t "renders overview page grammar" --run
red run before implementation: 1 failed
failure: overview decision console did not render `BIL · 现金/短债 · 做多/防守`,
`QQQ · 纳斯达克 · 回避/做空代理`, or `HYG · 高收益信用 · 低配`.
exit code: 1

$ uv run pytest tests/unit/domains/macro_intel/test_macro_scenario_engine.py::test_build_macro_scenario_emits_funding_stress_trade_map -q
1 passed
exit code: 0

$ cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx -t "renders overview page grammar" --run
1 passed
exit code: 0

$ uv run ruff check src/parallax/domains/macro_intel/services/macro_scenario_engine.py tests/unit/domains/macro_intel/test_macro_scenario_engine.py
All checks passed
exit code: 0

$ uv run pytest tests/unit/domains/macro_intel/test_macro_scenario_engine.py tests/unit/domains/macro_intel/test_macro_regime_engine.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py -q
82 passed
exit code: 0

$ cd web && npm run test -- tests/unit/features/macro/model/macroPageRegistry.test.ts tests/unit/features/macro/model/macroRoutes.test.ts tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts tests/unit/features/macro/model/macroTableColumns.test.ts tests/component/features/macro/MacroRatesWorkbench.test.tsx tests/component/features/cockpit/ui/AppSidebar.test.tsx tests/component/features/macro/MacroShell.test.tsx tests/component/features/macro/MacroDataTable.test.tsx tests/component/features/macro/MacroModulePages.test.tsx --run
9 files passed, 57 tests passed
exit code: 0

$ cd web && npm run typecheck
exit code: 0

$ cd web && npm run lint
ESLint passed; architecture tests 13 files passed, 73 tests passed
exit code: 0

$ uv run pytest tests/unit/domains/macro_intel/test_macro_scenario_engine.py::test_build_macro_scenario_emits_funding_stress_trade_map -q
red run before implementation: 1 failed
failure: funding-stress `watch_triggers` lacked `time_window` and `severity`
fields for 24h/72h catalyst display.
exit code: 1

$ uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_module_view_preserves_watch_trigger_horizon_and_priority -q
red run before implementation: 1 failed
failure: module view `_evidence_item` dropped watch-trigger `time_window` and
`severity` fields before the API/frontend layer.
exit code: 1

$ cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx -t "renders overview page grammar" --run
red run before implementation: 1 failed
failure: overview decision console showed only `观察`, not `观察 · 24h · 高`.
exit code: 1

$ uv run pytest tests/unit/domains/macro_intel/test_macro_scenario_engine.py::test_build_macro_scenario_emits_funding_stress_trade_map -q
1 passed
exit code: 0

$ uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_module_view_preserves_watch_trigger_horizon_and_priority -q
1 passed
exit code: 0

$ cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx -t "renders overview page grammar" --run
1 passed
exit code: 0

$ uv run ruff check src/parallax/domains/macro_intel/services/macro_scenario_engine.py src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_scenario_engine.py tests/unit/domains/macro_intel/test_macro_module_views.py
All checks passed
exit code: 0

$ uv run pytest tests/unit/domains/macro_intel/test_macro_scenario_engine.py tests/unit/domains/macro_intel/test_macro_regime_engine.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py -q
83 passed
exit code: 0

$ cd web && npm run test -- tests/unit/features/macro/model/macroPageRegistry.test.ts tests/unit/features/macro/model/macroRoutes.test.ts tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts tests/unit/features/macro/model/macroTableColumns.test.ts tests/component/features/macro/MacroRatesWorkbench.test.tsx tests/component/features/cockpit/ui/AppSidebar.test.tsx tests/component/features/macro/MacroShell.test.tsx tests/component/features/macro/MacroDataTable.test.tsx tests/component/features/macro/MacroModulePages.test.tsx --run
9 files passed, 57 tests passed
exit code: 0

$ cd web && npm run typecheck
exit code: 0

$ cd web && npm run lint
ESLint passed; architecture tests 13 files passed, 73 tests passed
exit code: 0

$ cd web && npm run test:e2e -- tests/e2e/golden-paths/macro-responsive-audit.spec.ts --project=desktop-1366
1 passed
exit code: 0

$ Browser smoke at http://127.0.0.1:5173/macro
result: app shell and macro overview rendered with no console errors; direct dev page
does not show `今日决策台` without API auth because `/api/macro/modules/overview`
returns unauthorized outside the mocked e2e harness. Mocked e2e covers the decision
console route with `decision_console` payload.
exit code: 0

$ uv run pytest tests/unit/domains/macro_intel/test_macro_module_catalog.py::test_gdp_page_absorbs_consumer_spending_evidence_after_consumer_page_deletion tests/unit/domains/macro_intel/test_macro_module_views.py::test_gap_payloads_do_not_preserve_labels_for_implemented_source_gaps -q
red run before implementation: 2 failed
failures: `economy/gdp` stranded consumer PCE/saving/sentiment concepts and `personal_spending_missing` still had a dedicated missing-data label.
exit code: 1

$ uv run pytest tests/unit/domains/macro_intel/test_macro_module_catalog.py::test_gdp_page_absorbs_consumer_spending_evidence_after_consumer_page_deletion tests/unit/domains/macro_intel/test_macro_module_views.py::test_gap_payloads_do_not_preserve_labels_for_implemented_source_gaps -q
2 passed
exit code: 0

$ uv run pytest tests/unit/domains/macro_intel/test_macro_module_catalog.py::test_credit_stress_page_includes_rating_ladder_and_financial_conditions_evidence tests/unit/domains/macro_intel/test_macro_module_catalog.py::test_volatility_vix_page_includes_cross_asset_volatility_indexes -q
red run before implementation: 2 failed
failures: retained `credit/stress` and `volatility/vix` pages did not consume existing credit rating-ladder, financial-condition, or cross-asset volatility concepts.
exit code: 1

$ uv run pytest tests/unit/domains/macro_intel/test_macro_module_catalog.py::test_credit_stress_page_includes_rating_ladder_and_financial_conditions_evidence tests/unit/domains/macro_intel/test_macro_module_catalog.py::test_volatility_vix_page_includes_cross_asset_volatility_indexes -q
2 passed
exit code: 0

$ uv run python - <<'PY'
... concept usage scan over retained module configs ...
PY
result: implemented macro concepts absent from retained module pages dropped from 52 to 38 after consumer, credit, and volatility consolidation.
exit code: 0

$ uv run pytest tests/unit/domains/macro_intel/test_macro_migration_contract.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_cli_macro_commands.py tests/unit/test_api_macro_contract.py -q
141 passed
exit code: 0

$ uv run pytest tests/unit/domains/macro_intel/test_macro_module_catalog.py::test_real_rates_page_includes_full_tips_and_breakeven_curve_evidence tests/unit/domains/macro_intel/test_macro_module_catalog.py::test_inflation_page_includes_pce_deflator_and_survey_expectation_evidence -q
red run before implementation: 2 failed
failures: retained `rates/real-rates` and `economy/inflation` pages did not consume existing TIPS curve, breakeven curve, PCE, GDP deflator, or MICH concepts.
exit code: 1

$ uv run pytest tests/unit/domains/macro_intel/test_macro_module_catalog.py::test_real_rates_page_includes_full_tips_and_breakeven_curve_evidence tests/unit/domains/macro_intel/test_macro_module_catalog.py::test_inflation_page_includes_pce_deflator_and_survey_expectation_evidence -q
2 passed
exit code: 0

$ uv run pytest tests/unit/domains/macro_intel/test_macro_migration_contract.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_cli_macro_commands.py tests/unit/test_api_macro_contract.py -q
143 passed
exit code: 0

$ uv run python - <<'PY'
... concept usage scan over retained module configs ...
PY
result: implemented macro concepts absent from retained module pages dropped from 38 to 31 after rates and inflation consolidation.
exit code: 0

$ uv run pytest tests/unit/domains/macro_intel/test_macro_module_catalog.py::test_equities_page_includes_public_index_and_etf_risk_proxies tests/unit/domains/macro_intel/test_macro_module_catalog.py::test_bonds_page_includes_duration_inflation_and_credit_etf_proxies tests/unit/domains/macro_intel/test_macro_module_catalog.py::test_commodities_page_includes_public_spot_futures_and_etf_proxies tests/unit/domains/macro_intel/test_macro_module_catalog.py::test_fx_page_includes_public_fred_yahoo_and_currency_etf_proxies -q
red run before implementation: 4 failed
failures: retained asset pages did not consume existing public equity index/ETF, bond ETF, commodity spot/futures/ETF, or FX concepts.
exit code: 1

$ uv run pytest tests/unit/domains/macro_intel/test_macro_module_catalog.py::test_equities_page_includes_public_index_and_etf_risk_proxies tests/unit/domains/macro_intel/test_macro_module_catalog.py::test_bonds_page_includes_duration_inflation_and_credit_etf_proxies tests/unit/domains/macro_intel/test_macro_module_catalog.py::test_commodities_page_includes_public_spot_futures_and_etf_proxies tests/unit/domains/macro_intel/test_macro_module_catalog.py::test_fx_page_includes_public_fred_yahoo_and_currency_etf_proxies -q
4 passed
exit code: 0

$ uv run pytest tests/unit/domains/macro_intel/test_macro_module_catalog.py::test_fed_funds_page_includes_daily_effective_fed_funds_evidence tests/unit/domains/macro_intel/test_macro_module_catalog.py::test_gdp_and_employment_pages_include_remaining_growth_and_labor_evidence tests/unit/domains/macro_intel/test_macro_module_catalog.py::test_equities_page_includes_global_sector_and_positioning_proxies -q
red run before implementation: 3 failed
failures: retained pages did not consume existing DFF, nominal GDP, industrial production, housing starts, labor participation, global/sector equity ETFs, or CFTC S&P 500 positioning concepts.
exit code: 1

$ uv run pytest tests/unit/domains/macro_intel/test_macro_module_catalog.py::test_fed_funds_page_includes_daily_effective_fed_funds_evidence tests/unit/domains/macro_intel/test_macro_module_catalog.py::test_gdp_and_employment_pages_include_remaining_growth_and_labor_evidence tests/unit/domains/macro_intel/test_macro_module_catalog.py::test_equities_page_includes_global_sector_and_positioning_proxies -q
3 passed
exit code: 0

$ uv run pytest tests/unit/domains/macro_intel/test_macro_migration_contract.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_cli_macro_commands.py tests/unit/test_api_macro_contract.py -q
150 passed
exit code: 0

$ uv run python - <<'PY'
... concept usage scan over retained module configs ...
PY
result: implemented macro concepts absent from retained module pages dropped from 31 to 0.
exit code: 0

$ cd /Users/qinghuan/Documents/code/macrodata-cli && uv run mypy src tests
interrupted after more than two minutes with no output; no result recorded.

$ cd /Users/qinghuan/Documents/code/macrodata-cli && uv run mypy src/macrodata/core/errors.py src/macrodata/core/models.py src/macrodata/providers/fred.py src/macrodata/app/services.py tests/unit/test_bundles.py tests/cli/test_bundle_commands.py
interrupted after more than ninety seconds with no output; no result recorded.

$ cd web && npm run test:e2e -- tests/e2e/golden-paths/macro-responsive-audit.spec.ts --project=desktop-1366
1 passed
exit code: 0
```

## Coverage

| metric | value   | threshold | status         |
| ------ | ------- | --------- | -------------- |
| line   | Not run | >= 80%    | not applicable |
| branch | Not run | >= 70%    | not applicable |

## Skipped tests

Number of skipped tests in the run above: Not run

## E2E golden path

- [x] /macro renders at desktop width.
- [x] /macro decision console renders at mobile width without overlap in mocked browser smoke.
- [x] Retained primary child routes remain reachable.
- [x] Deleted macro routes are absent from navigation and route registry.
- [x] No browser console/pageerror failures in macro smoke.

## Completion Gate

```text
$ make check-sdd-completion FEATURE=2026-06-16-macro-decision-console
not run
exit code: not run
```

## Other Commands Run

```text
$ uv run parallax config
exit code: 0

$ uv run parallax macro status
exit code: 0

$ uv run macrodata doctor
exit code: 0

$ uv run macrodata bundle macro-core --asof 2026-06-16
exit code: 0

$ cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest tests/provider/test_official_calendar_provider.py tests/unit/test_bundles.py::test_macro_calendar_core_is_separate_from_numeric_regime_bundle tests/unit/test_catalog.py::test_catalog_contains_official_calendar_event_series tests/unit/test_runtime.py::test_runtime_wires_official_calendar_provider tests/cli/test_bundle_commands.py::test_macro_calendar_core_bundle_fetch_uses_official_sources -q
exit code: 4
red evidence: collection failed because `macrodata.providers.official_calendar`
and `MACRO_CALENDAR_CORE` did not exist.

$ cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest tests/provider/test_official_calendar_provider.py tests/unit/test_bundles.py::test_macro_calendar_core_is_separate_from_numeric_regime_bundle tests/unit/test_catalog.py::test_catalog_contains_official_calendar_event_series tests/unit/test_runtime.py::test_runtime_wires_official_calendar_provider tests/cli/test_bundle_commands.py::test_macro_calendar_core_bundle_fetch_uses_official_sources -q
exit code: 0
8 passed in 0.76s

$ cd /Users/qinghuan/Documents/code/macrodata-cli && uv run ruff check src/macrodata/providers/official_calendar.py src/macrodata/gateway/http_client.py src/macrodata/app/runtime.py src/macrodata/app/services.py src/macrodata/surfaces/cli.py tests/provider/test_official_calendar_provider.py tests/unit/test_bundles.py tests/unit/test_catalog.py tests/unit/test_runtime.py tests/cli/test_bundle_commands.py
exit code: 0
All checks passed!

$ cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest tests/provider/test_official_calendar_provider.py tests/unit/test_bundles.py tests/unit/test_catalog.py tests/unit/test_runtime.py tests/cli/test_bundle_commands.py -q
exit code: 0
48 passed in 9.66s

$ cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest -q
exit code: 0
117 passed in 9.98s

$ cd /Users/qinghuan/Documents/code/macrodata-cli && uv run ruff check .
exit code: 0
All checks passed!

$ cd /Users/qinghuan/Documents/code/macrodata-cli && uv run macrodata bundle fetch macro-calendar-core --asof 2026-06-16
exit code: 0
real public-source smoke after Task 34: `coverage={"requested":6,"available":6}`,
`data_quality="ok"`, no missing series. Observations returned
`official_calendar:fomc_decision_next` for 2026-06-17,
`official_calendar:bea_gdp_next` / `official_calendar:bea_pce_next` for
2026-06-25, `official_calendar:bls_employment_next` for 2026-07-02,
`official_calendar:bls_cpi_next` for 2026-07-14, and
`official_calendar:bls_ppi_next` for 2026-07-15. BLS provenance includes
official `source_url`, `event_time_et="08:30 AM"`, and
`reference_period="June 2026"`.

$ cd /Users/qinghuan/Documents/code/macrodata-cli && uv run mypy src tests
exit code: 143
manual stop after repeated no-output hang; even `uv run mypy --version` hung
and was stopped with exit code 143.

$ uv run python scripts/validate_sdd_artifacts.py
exit code: 1
remaining failures are active-touch conflicts and one uncited-background issue
in `2026-06-12-kappa-cqrs-governance-root-fix`; no task-complete errors remain
for this feature after the latest task-status correction.

$ uv run pytest tests/unit/domains/macro_intel/test_macro_module_catalog.py::test_catalog_has_no_static_source_backlog_gap_codes tests/unit/domains/macro_intel/test_macro_module_views.py::test_build_macro_module_view_returns_missing_v3_status_when_snapshot_is_absent -q
red run before implementation: 2 failed
failures: retained modules still carried static source-backlog `gap_codes`, and
missing snapshot views still injected `fomc_calendar_missing`.
exit code: 1

$ uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_gap_payloads_do_not_preserve_labels_for_retired_source_backlog_codes -q
red run before implementation: 1 failed
failure: retired source-backlog codes still preserved specialized labels such
as MOVE, Fed calendar, and VIX term structure.
exit code: 1

$ cd web && npm run test -- tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts tests/component/features/macro/MacroRatesWorkbench.test.tsx --run
red run before implementation: 2 failed, 17 passed
failures: `rates/expectations` still rendered proxy readiness and the old
"当前为政策路径代理页面" headline.
exit code: 1

$ uv run pytest tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/domains/macro_intel/test_macro_daily_brief.py -q
70 passed
exit code: 0

$ cd web && npm run test -- tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts tests/component/features/macro/MacroRatesWorkbench.test.tsx --run
2 files passed, 19 tests passed
exit code: 0

$ cd web && npm run typecheck
exit code: 0

$ cd web && npm run lint
ESLint passed; architecture tests 13 files passed, 73 tests passed
exit code: 0

$ cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest tests/unit/test_http_client.py::test_http_client_disables_environment_proxy_settings tests/provider/test_treasury_auction_provider.py tests/unit/test_catalog.py::test_catalog_contains_treasury_auction_result_series tests/unit/test_runtime.py::test_runtime_wires_treasury_auction_provider tests/unit/test_bundles.py::test_treasury_auction_core_is_separate_from_numeric_regime_bundle tests/unit/test_bundles.py::test_focused_macro_terminal_bundles_collect_observations tests/cli/test_bundle_commands.py::test_treasury_auction_core_bundle_fetch_uses_official_fiscaldata -q
red run before implementation: collection failed
failures: missing `macrodata.providers.treasury_auction` and missing
`TREASURY_AUCTION_CORE`.
exit code: 4

$ cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest tests/unit/test_http_client.py::test_http_client_disables_environment_proxy_settings tests/provider/test_treasury_auction_provider.py tests/unit/test_catalog.py::test_catalog_contains_treasury_auction_result_series tests/unit/test_runtime.py::test_runtime_wires_treasury_auction_provider tests/unit/test_bundles.py::test_treasury_auction_core_is_separate_from_numeric_regime_bundle tests/unit/test_bundles.py::test_focused_macro_terminal_bundles_collect_observations tests/cli/test_bundle_commands.py::test_treasury_auction_core_bundle_fetch_uses_official_fiscaldata -q
14 passed
exit code: 0

$ cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest tests/unit/test_http_client.py tests/provider/test_treasury_auction_provider.py tests/unit/test_catalog.py tests/unit/test_runtime.py tests/unit/test_bundles.py tests/cli/test_bundle_commands.py -q
58 passed
exit code: 0

$ cd /Users/qinghuan/Documents/code/macrodata-cli && uv run ruff check .
All checks passed
exit code: 0

$ cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest -q
126 passed
exit code: 0

$ cd /Users/qinghuan/Documents/code/macrodata-cli && uv run macrodata bundle fetch treasury-auction-core --asof 2026-06-16
summary: ok=true; bundle=treasury-auction-core; coverage requested=9 available=9;
source_chain=treasury_auction; data_quality=ok; first observation
treasury_auction:2y_high_yield observed_at=2026-05-26 value=4.071.
exit code: 0
```

### Task 17 — Parallax Official Event Import/Rendering

Red evidence:

```text
$ uv run pytest tests/unit/domains/macro_intel/test_macrodata_bundle_importer.py::test_import_macrodata_bundle_accepts_event_bundles_without_expanding_numeric_macro_core tests/unit/domains/macro_intel/test_macro_view_projection_worker.py::test_macro_view_projection_worker_event_targets_refresh_without_numeric_snapshot tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_module_view_adds_official_event_catalysts_to_decision_console tests/unit/test_api_macro_contract.py::test_macro_overview_module_api_loads_event_concepts_for_decision_console -q
FFFF [100%]
failures: importer rejected `official_calendar:fomc_decision_next` as an
unknown macro-core series; event dirty targets still rebuilt numeric snapshots;
overview module view had no `event_catalysts`; overview API did not request
event concepts.

$ cd web && npm run test -- MacroModulePages.test.tsx -t "renders overview page grammar" --run
1 failed | 5 skipped
failure: unable to find region "事件催化".
```

Green evidence:

```text
$ uv run pytest tests/unit/domains/macro_intel/test_macrodata_bundle_importer.py::test_import_macrodata_bundle_accepts_event_bundles_without_expanding_numeric_macro_core tests/unit/domains/macro_intel/test_macro_view_projection_worker.py::test_macro_view_projection_worker_event_targets_refresh_without_numeric_snapshot tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_module_view_adds_official_event_catalysts_to_decision_console tests/unit/test_api_macro_contract.py::test_macro_overview_module_api_loads_event_concepts_for_decision_console -q
.... [100%]
4 passed in 0.93s

$ cd web && npm run test -- MacroModulePages.test.tsx -t "renders overview page grammar" --run
Test Files  1 passed (1)
Tests  1 passed | 5 skipped (6)
```

Expanded verification:

```text
$ uv run pytest tests/unit/domains/macro_intel/test_macrodata_bundle_importer.py tests/unit/domains/macro_intel/test_macro_view_projection_worker.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/architecture/test_macro_no_compatibility_contract.py -q
144 passed in 1.49s

$ cd web && npm run test -- MacroModulePages.test.tsx MacroRatesWorkbench.test.tsx macroPageRegistry.test.ts macroRoutes.test.ts --run
Test Files  4 passed (4)
Tests  25 passed (25)

$ cd web && npm run lint
Test Files  13 passed (13)
Tests  73 passed (73)

$ cd web && npm run test:architecture
Test Files  13 passed (13)
Tests  73 passed (73)

$ cd web && npm run typecheck
exit code: 0

$ uv run ruff check src/parallax/domains/macro_intel/_constants.py src/parallax/domains/macro_intel/services/macrodata_bundle_importer.py src/parallax/domains/macro_intel/runtime/macro_view_projection_worker.py src/parallax/domains/macro_intel/services/macro_module_catalog.py src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macrodata_bundle_importer.py tests/unit/domains/macro_intel/test_macro_view_projection_worker.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py
All checks passed!
```

## Diff Summary

Files changed during planning and hard-deletion implementation:

- `docs/sdd/features/active/2026-06-16-macro-decision-console/spec.md`
- `docs/sdd/features/active/2026-06-16-macro-decision-console/plan.md`
- `docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md`
- `docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md`
- `src/parallax/domains/macro_intel/services/macro_module_catalog.py`
- `src/parallax/domains/macro_intel/services/macro_module_views.py`
- `src/parallax/domains/macro_intel/runtime/macro_view_projection_worker.py`
- `src/parallax/domains/macro_intel/_constants.py`
- `src/parallax/app/surfaces/api/routes_macro.py`
- `src/parallax/domains/macro_intel/services/macro_gap_payloads.py`
- `web/src/features/macro/model/*`
- `web/src/features/macro/ui/rates/*`
- `web/src/features/macro/ui/workbench/MacroDecisionConsolePanel.tsx`
- `web/src/features/macro/ui/shell/MacroShell.tsx`
- Macro contract, architecture, and focused backend/frontend tests.
- `/Users/qinghuan/Documents/code/macrodata-cli/src/macrodata/core/errors.py`
- `/Users/qinghuan/Documents/code/macrodata-cli/src/macrodata/core/models.py`
- `/Users/qinghuan/Documents/code/macrodata-cli/src/macrodata/providers/fred.py`
- `/Users/qinghuan/Documents/code/macrodata-cli/src/macrodata/providers/official_calendar.py`
- `/Users/qinghuan/Documents/code/macrodata-cli/src/macrodata/gateway/http_client.py`
- `/Users/qinghuan/Documents/code/macrodata-cli/src/macrodata/app/runtime.py`
- `/Users/qinghuan/Documents/code/macrodata-cli/src/macrodata/catalog/entries.py`
- `/Users/qinghuan/Documents/code/macrodata-cli/src/macrodata/surfaces/cli.py`
- `/Users/qinghuan/Documents/code/macrodata-cli/src/macrodata/app/services.py`
- `/Users/qinghuan/Documents/code/macrodata-cli/tests/provider/test_official_calendar_provider.py`
- `/Users/qinghuan/Documents/code/macrodata-cli/tests/unit/test_catalog.py`
- `/Users/qinghuan/Documents/code/macrodata-cli/tests/unit/test_runtime.py`
- `/Users/qinghuan/Documents/code/macrodata-cli/tests/unit/test_bundles.py`
- `/Users/qinghuan/Documents/code/macrodata-cli/tests/cli/test_bundle_commands.py`
- `/Users/qinghuan/Documents/code/macrodata-cli/AGENTS.md`
- `/Users/qinghuan/Documents/code/macrodata-cli/README.md`
- `/Users/qinghuan/Documents/code/macrodata-cli/docs/reference/result-envelope.md`
- `/Users/qinghuan/Documents/code/macrodata-cli/docs/reference/catalog.md`
- `/Users/qinghuan/Documents/code/macrodata-cli/docs/reference/mcp-tools.md`

Migrations applied:

- None.

Schema or contract changes that consumers must be aware of:

- Parallax `/api/macro` overview module read now includes
  `module_read.decision_console`.
- Parallax overview `module_read.decision_console` now may include
  `event_catalysts`, built from persisted `event:*` macro observations. The
  frontend renders those catalysts as an "事件催化" section and does not derive
  event text locally.
- Parallax `macro import-bundle` can now accept standalone macrodata event
  bundles for official Fed/BEA/BLS calendar events and completed Treasury auction
  results. These are mapped to `event:*` concepts, remain outside numeric
  `MACRO_CORE_CONCEPTS`, and event-only dirty targets refresh
  `macro_observation_series_rows` without rebuilding `macro_regime_v4`.
- External `macrodata-cli` bundle snapshots now include `source_health`; FRED
  observations and FRED series errors may include redacted `access_mode`.
- External `macrodata-cli` now includes `official_calendar` provider and
  standalone `macro-calendar-core` bundle with next-event official catalysts:
  FOMC decision, GDP, Personal Income and Outlays/PCE, BLS CPI, BLS Employment
  Situation, and BLS PPI. Calendar observations use event date as `observed_at`,
  `days_until` as value, and official source URL/title/time in provenance. BLS
  observations additionally preserve the official reference period. They
  are deliberately excluded from numeric `macro-core`; Parallax imports them as
  event catalysts so regime history is not polluted by future event observations.
- External `macrodata-cli` `credit-core` and Parallax macro concepts now include
  FRED SLOOS C&I lending standards and demand series: `DRTSCILM`, `DRTSCIS`,
  `DRSDCILM`, and `DRSDCIS`.
- External `macrodata-cli` `credit-core` and Parallax macro concepts now include
  FRED loan-quality delinquency and charge-off series: `DRBLACBS`, `DRCLACBS`,
  `CORBLACBS`, and `CORCACBS`.
- External `macrodata-cli` `volatility-core` and Parallax `volatility/vix` now
  include the Yahoo VIXM mid-term VIX futures ETF proxy as `asset:vixm` and
  the Yahoo `^MOVE` rates-volatility proxy as `vol:move`; the VIX futures curve
  and licensed ICE/Bloomberg MOVE source gaps remain visible.
- External `macrodata-cli` `economy-core` and Parallax `economy/employment` now
  include FRED/BLS average hourly earnings (`CES0500000003`) and render already
  cataloged JOLTS (`JTSJOL`) as page evidence rather than future gaps.
- Parallax `economy/gdp` now absorbs existing consumer PCE, real PCE, saving
  rate, and UMich sentiment facts after the hard deletion of `economy/consumer`;
  `personal_spending_missing` no longer has a dedicated source-gap label.
- Parallax `credit/stress` now absorbs existing credit rating-ladder OAS,
  STLFSI/NFCI/ANFCI, and public loan/SLOOS evidence without restoring deleted
  CDS/dealer surfaces.
- Parallax `volatility/vix` now absorbs existing VXN/RVX/GVZ/OVX/EVZ cross-asset
  volatility indexes without restoring the deleted volatility dashboard.
- Parallax `rates/real-rates` now absorbs existing 5Y/10Y/30Y TIPS and 5Y/10Y/5Y5Y
  inflation compensation concepts.
- Parallax `economy/inflation` now absorbs existing PCE/core PCE, GDP deflator,
  MICH expectation, and market inflation compensation concepts.
- Parallax retained module catalog now consumes every implemented macro-core
  concept at least once across the retained pages; the orphan implemented-concept
  scan reports `count=0`.
- Parallax scenario generation now fills `top_changes` from source-backed
  feature deltas for priority macro concepts when explicit trigger rules are
  quiet, so `/macro` does not lose the timsun-style "3 个最重要变化" block in
  non-threshold regimes.
- Parallax macro workbench localizes known Trade Map confirm/invalidates signal
  codes such as `sofr_above_iorb`, `hy_oas_widening_5d`, and
  `sofr_iorb_normalizes`; the overview decision console no longer shows
  `待确认信号` for known macro rules.
- Parallax scenario Trade Map entries now include deterministic asset legs, and
  the overview renders them as visible actions such as `BIL · 现金/短债 · 做多/防守`,
  `QQQ · 纳斯达克 · 回避/做空代理`, and `HYG · 高收益信用 · 低配`.
- Parallax scenario watch triggers now carry `time_window` and `severity`, module
  views preserve those fields, and the overview renders catalyst context such
  as `观察 · 24h · 高`.
- Parallax retained modules no longer carry static source-backlog `gap_codes`;
  unavailable source domains such as licensed MOVE, VIX futures curve, GEX, Fed futures,
  Fed text delta scoring, and Treasury auction tail remain in SDD/source backlog only until implemented.
  Runtime module gaps are now reserved for actual
  missing/stale observations, chart blockers, and global projection blockers.
- Parallax backend gap payloads no longer preserve specialized labels or
  remediation strings for retired source-backlog codes. Old codes that appear
  in historical snapshots fall through to generic data-gap handling instead of
  reviving deleted product promises.
- The web rates workbench no longer has a Fed futures/FOMC probability
  proxy-page branch driven by `fed_funds_futures_missing` or
  `fomc_probability_feed_missing`. `rates/expectations` is now hard-deleted
  from the backend module catalog, frontend route registry, navigation, fixtures,
  and e2e route set until legal source-backed meeting probabilities exist.
- External `macrodata-cli` now includes a `treasury_auction` provider backed by
  the official U.S. Treasury FiscalData `auctions_query` API, plus a standalone
  `treasury-auction-core` bundle with completed 2Y/10Y/30Y auction high yield,
  bid-to-cover, and indirect bidder accepted percentage observations. These
  event observations are deliberately excluded from numeric `macro-core`.
- External `macrodata-cli` `MacrodataHttpClient` now uses `trust_env=False` for
  HTTP requests. Project-runtime investigation showed FiscalData succeeds with
  `trust_env=False`, while `trust_env=True` times out during TLS handshake in
  this environment.
- External `macrodata-cli` now exposes first-class history commands for
  `macro-calendar-core` and `treasury-auction-core`, so Parallax can call them
  through the same `macrodata bundle history <bundle>` child-process contract
  used for `macro-core`.
- External `macrodata-cli` bundle history now treats windows with zero
  observations as `unavailable` with `missing_series`, `no_observations`, and
  `all_series_missing` instead of reporting `data_quality=ok`.
- Parallax `workers.macro_sync` now uses formal `bundle_names` instead of the
  old single `bundle_name` setting. The default set is `macro-core`,
  `macro-calendar-core`, `treasury-auction-core`, and `fed-text-core`;
  `MacroSyncService` enqueues due windows for every configured bundle through
  `macro_sync_windows`.
- Parallax `macro status` now asks `macrodata_runtime_state` to verify the
  configured sync bundles. Task 18 first proved stale-package detection for the
  calendar/auction event set; Task 31 temporarily made `fed-text-core` required
  before the dependency was repinned; Task 32 repinned Parallax to macrodata-cli
  `0.1.11`, so all four configured bundles are now available in the Parallax
  venv.

## Task 18 Verification — Scheduled Official Event Bundles

Red tests:

- `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest tests/cli/test_bundle_commands.py::test_event_bundle_history_commands_are_first_class_sync_surfaces -q` initially failed with Typer exit 2 because `bundle history macro-calendar-core` was not a command.
- `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest tests/unit/test_bundles.py::test_bundle_history_marks_empty_series_windows_unavailable -q` initially failed because an all-empty history window produced no `missing_series`.
- `uv run pytest tests/unit/domains/macro_intel/test_macro_sync_service.py::test_sync_service_enqueue_due_windows_schedules_all_configured_product_bundles tests/unit/test_worker_settings.py::test_default_workers_yaml_contains_canonical_worker_defaults tests/architecture/test_worker_runtime_contracts.py::test_macro_sync_worker_and_service_use_formal_settings_wake_contract_without_runtime_defaults -q` initially failed because Parallax still had single-bundle `bundle_name` settings and service scheduling.
- `uv run pytest tests/unit/test_cli_macro_commands.py::test_macrodata_runtime_state_reports_missing_configured_sync_bundles -q` initially failed because `macrodata_runtime_state` did not accept `required_bundles`.

Green tests and smokes:

- `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest tests/cli/test_bundle_commands.py tests/unit/test_bundles.py tests/provider/test_official_calendar_provider.py tests/provider/test_treasury_auction_provider.py -q` -> `38 passed`.
- `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run ruff check src/macrodata/surfaces/cli.py src/macrodata/app/services.py tests/cli/test_bundle_commands.py tests/unit/test_bundles.py` -> pass.
- `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run macrodata bundle history macro-calendar-core --start 2026-06-16 --end 2026-07-31` -> `ok=true`, command `bundle.macro-calendar-core-history`, source-backed FOMC/BEA event observations.
- `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run macrodata bundle history treasury-auction-core --start 2026-05-01 --end 2026-06-16` -> `ok=true`, `data_quality=ok`, requested 9, available 9.
- `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run macrodata bundle history treasury-auction-core --start 2026-06-01 --end 2026-06-30` -> `ok=true`, `data_quality=unavailable`, requested 9, available 0, reason codes `missing_series`, `no_observations`, `all_series_missing`.
- `uv run pytest tests/unit/test_cli_macro_commands.py tests/unit/domains/macro_intel/test_macro_sync_service.py tests/unit/domains/macro_intel/test_macro_sync_worker.py tests/unit/domains/macro_intel/test_macro_sync_scheduler.py tests/unit/test_worker_settings.py tests/architecture/test_worker_runtime_contracts.py::test_macro_sync_worker_and_service_use_formal_settings_wake_contract_without_runtime_defaults -q` -> `101 passed`.
- `uv run ruff check src/parallax/domains/macro_intel/services/macro_sync_service.py src/parallax/platform/config/settings.py src/parallax/integrations/macrodata/runner.py src/parallax/app/surfaces/cli/commands/macro.py tests/unit/domains/macro_intel/test_macro_sync_service.py tests/unit/test_cli_macro_commands.py tests/unit/test_worker_settings.py tests/architecture/test_worker_runtime_contracts.py` -> pass.
- Task 17 runtime-state probe: `uv run python - <<'PY' ... macrodata_runtime_state(required_bundles=(...)) ... PY` in the Parallax venv reported installed `macrodata-cli 0.1.9`, required bundle count 3, missing bundle count 0, `required_bundles_available=true`, and no missing bundles for the then-current calendar/auction event set. Task 31 extended the source-code default to four bundles; Task 32 repinned the dependency so `fed-text-core` is available before Fed text catalyst sync runs.
- Before Task 34 packaging/repin, `uv run macrodata bundle history macro-calendar-core --start 2026-06-16 --end 2026-07-31` in the Parallax venv reported command `bundle.macro-calendar-core-history`, bundle `macro-calendar-core`, `data_quality=ok`, requested 3, available 3, and 6 Fed/BEA event observations.
- `uv run macrodata bundle history treasury-auction-core --start 2026-05-01 --end 2026-06-16` in the Parallax venv reports command `bundle.treasury-auction-core-history`, bundle `treasury-auction-core`, `data_quality=ok`, requested 9, available 9, and 9 event observations.

## Live Runtime Refresh — 2026-06-16

Commands used the operator runtime config reported by `uv run parallax config`:
`/Users/qinghuan/.parallax/config.yaml` and
`/Users/qinghuan/.parallax/workers.yaml`. Macrodata is enabled and FRED is
configured through the named environment setting; no secret values were printed
or copied.

Red/live blocker:

- `uv run parallax macro sync --bundle macro-core --start 2024-06-01 --end 2026-06-16` initially failed with `ValueError: Out of range float values are not JSON compliant: nan` while writing JSONB payloads from macrodata history observations.
- `uv run pytest tests/unit/domains/macro_intel/test_macrodata_bundle_importer.py::test_import_macrodata_bundle_sanitizes_non_finite_numbers_before_jsonb_write -q` failed before implementation with the same JSON serialization error.
- `uv run pytest tests/unit/domains/macro_intel/test_macro_migration_contract.py::test_quarterly_credit_history_thresholds_match_quarterly_release_cadence -q` failed before implementation because SLOOS and loan-quality quarterly credit concepts did not have release-cadence history thresholds.

Fixes verified:

- `macrodata_bundle_importer` now recursively sanitizes non-finite floats and
  Decimals before JSONB writes. `value_numeric` becomes `None` for NaN/Infinity,
  while finite Decimal values remain numeric for facts and finite Decimal values
  in raw payloads become JSON-safe floats.
- Quarterly SLOOS and loan-quality concepts use an 8-point history threshold,
  matching their release cadence instead of daily/weekly expectations.
- `uv run pytest tests/unit/domains/macro_intel/test_macrodata_bundle_importer.py -q` -> `18 passed`.
- `uv run pytest tests/unit/domains/macro_intel/test_macro_migration_contract.py::test_quarterly_credit_history_thresholds_match_quarterly_release_cadence -q` -> pass.

Live sync and projection:

- `uv run parallax db health` -> migration ready at `20260612_0179`.
- Before Task 34 packaging/repin, `uv run parallax macro sync --bundle macro-calendar-core --start 2026-06-16 --end 2026-07-31` -> `ok=true`, imported 6 official Fed/BEA event observations.
- `uv run parallax macro sync --bundle treasury-auction-core --start 2026-05-01 --end 2026-06-16` -> `ok=true`, imported 9 Treasury auction result observations.
- After the JSONB sanitizer fix, `uv run parallax macro sync --bundle macro-core --start 2024-06-01 --end 2026-06-16` -> `ok=true`, `status=partial`, imported/changed 35,933 observations with max observed date `2026-06-16`.
- A current macro view dirty target was enqueued and processed by `MacroViewProjectionWorker`; the rebuilt snapshot scanned 61,057 source rows, loaded 138 targets, wrote the current snapshot, and published series rows. `MacroDailyBriefProjectionWorker` then refreshed the daily brief.
- To make the retained product usable rather than merely partially populated,
  `uv run parallax macro sync --bundle macro-core --start 2023-06-16 --end 2026-06-16`
  was run after the sanitizer fix. It exited `ok=true`, imported/changed
  28,945 observations, and kept max observed date `2026-06-16`.
- The current macro view was rebuilt again through `MacroViewProjectionWorker`.
  The worker scanned 77,835 source rows, loaded 138 targets, wrote the current
  snapshot, and reported `status=ready` with `history_coverage_ratio=1.0`.
  `MacroDailyBriefProjectionWorker` reported `status=ready`.

Live status after refresh:

- Before Task 31, `uv run parallax macro status` reported macrodata package `0.1.9`, required bundle count 3, missing required bundle count 0, observations count 81,508, concept count 150, `history_ready=true`, latest snapshot status `ready`, feature count 138, as-of date `2026-06-16`, history coverage ratio `1.0`, and no concepts below minimum history. After Task 32, `uv run parallax macro status` reports macrodata-cli `0.1.11`, required bundle count 4, missing required bundle count 0, `required_bundles_available=true`, 81,539 observations, 153 concepts, latest snapshot status `ready`, and projection lag `0`.
- The selected newly added concepts are live in facts and projection: `asset:vixm`, `labor:avg_hourly_earnings`, SLOOS C&I tightening/demand, business/consumer delinquency and charge-off, Fed/BEA event catalysts, and 2Y/10Y/30Y Treasury auction event metrics.
- Current-code overview module payload renders 6 `event_catalysts`: BEA GDP, BEA PCE, FOMC decision, and 10Y Treasury auction bid-to-cover/high-yield/indirect-bidder metrics.
- Current-code retained module payloads render new evidence rows: `credit/stress` includes SLOOS and loan-quality rows, `volatility/vix` includes VIXM/VIXY/VIX3M rows, and `economy/employment` includes payrolls, JOLTS job openings, average hourly earnings, and initial claims.

Post-refresh verification:

- `uv run pytest tests/unit/domains/macro_intel/test_macrodata_bundle_importer.py tests/unit/domains/macro_intel/test_macro_migration_contract.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/domains/macro_intel/test_macro_scenario_engine.py tests/unit/domains/macro_intel/test_macro_sync_service.py tests/unit/test_api_macro_contract.py tests/unit/test_cli_macro_commands.py -q` -> `201 passed`.
- `uv run ruff check .` -> pass.
- `uv run ruff format --check src/parallax/domains/macro_intel/services/macro_module_views.py src/parallax/domains/macro_intel/services/macro_scenario_engine.py tests/architecture/test_worker_runtime_contracts.py tests/unit/domains/macro_intel/test_macro_migration_contract.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/domains/macro_intel/test_macrodata_bundle_importer.py tests/unit/test_api_macro_contract.py` -> pass. Full-repo Python format remains blocked by unrelated baseline files outside this macro slice.
- `uv run python -m compileall src tests` -> pass.
- `cd web && npm run test -- tests/unit/features/macro/model/macroPageRegistry.test.ts tests/unit/features/macro/model/macroRoutes.test.ts tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts tests/unit/features/macro/model/macroTableColumns.test.ts tests/component/features/macro/MacroRatesWorkbench.test.tsx tests/component/features/cockpit/ui/AppSidebar.test.tsx tests/component/features/macro/MacroShell.test.tsx tests/component/features/macro/MacroDataTable.test.tsx tests/component/features/macro/MacroModulePages.test.tsx --run` -> 9 files passed, 57 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run lint` -> ESLint passed and architecture tests 13 files passed, 73 tests passed.
- `cd web && npm run format:check` -> pass.
- `cd web && npm run test:e2e -- tests/e2e/golden-paths/macro-responsive-audit.spec.ts --project=desktop-1366` -> 1 passed.
- `cd web && npm run test:e2e -- tests/e2e/golden-paths/macro-terminal.spec.ts --project=desktop-1366 -g "hard-deleted routes"` -> 1 passed after expanding the e2e guard to cover every hard-deleted macro route.
- `cd web && npm run test:e2e -- tests/e2e/golden-paths/macro-terminal.spec.ts --project=desktop-1366` -> 4 passed, 1 mobile-only test skipped in the desktop project; the deleted-route case now loops through `/macro/assets/crypto-derivatives`, `/macro/rates/auctions`, `/macro/rates/expectations`, `/macro/fed/statements`, `/macro/fed/speeches`, `/macro/liquidity/global-dollar`, `/macro/liquidity/subsurface`, `/macro/economy/consumer`, `/macro/volatility/dashboard`, and `/macro/credit/cds` and asserts the ordinary `404 Not Found` route-error surface with no macro module nav.
- `uv run python scripts/regen_sdd_work_index.py --check` -> pass.
- `uv run python scripts/validate_sdd_artifacts.py` -> pass after adding explicit coordination with `2026-06-12-kappa-cqrs-governance-root-fix` and fixing that feature's cited-background lines.
- `uv run python scripts/regen_ws_protocol.py --check` -> pass after regenerating `docs/generated/ws-protocol.md`.
- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_transmission_uses_display_labels_for_chain_nodes_and_regimes -q` -> pass; overview transmission nodes now display labels such as `政策走廊`, `跨资产确认`, and `仓位拥挤度` and do not surface `fed_corridor`, `cross_asset`, `positioning`, or `未知宏观状态`.
- Current-code live DB probe through `build_macro_module_view("overview", ...)` reports snapshot status `ready`, 7 transmission nodes, and user-facing labels `利率定价`, `信用压力`, `美元流动性`, `波动率`, `跨资产确认`, `仓位拥挤度`, and `政策走廊`; the displayed regime values no longer include `未知宏观状态`.
- A Task-40-preceding read-only live DB module audit through the same
  `build_macro_module_view(...)` path used by `/api/macro/modules/{module_id}`
  checked all 21 retained macro module ids. The current snapshot was `ready`
  as of `2026-06-16`, every retained module returned `status=ready`, every
  primary chart returned `status=ok`, every retained non-overview module had
  table rows, no related route pointed at a hard-deleted URL, and no
  user-facing label/value/detail/headline/meta text contained deleted route
  slugs or internal labels such as `fed_corridor`, `cross_asset`,
  `positioning`, or `未知宏观状态`. The legacy future-source bucket was empty for
  all retained modules; remaining `module_gaps` and `global_gaps` are actual
  stale/missing/latest-window diagnostics.
- TDD display-ready cleanup: `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_module_view_surfaces_global_scenario_and_data_health -q` first failed because `decision_console.top_changes[].node` still exposed internal node ids such as `rates`/`funding`. After mapping compact signal nodes through backend display labels, the test passed. A live DB probe now reports top changes with nodes `资金面`, `资金面`, and `跨资产确认`, with no raw node values in that display field.
- TDD frontend display-label cleanup: `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts --run` first failed because backend display labels `资金面` and `跨资产确认` were remapped to the generic label `宏观`. `sectionLabel(...)` now preserves backend-provided Chinese display labels and maps remaining internal compact nodes such as `cross_asset`, `fed_corridor`, and `positioning` to product labels. The targeted unit test, overview component test, and `npm run typecheck` all pass.
- Isolated current-worktree browser QA used a temporary API on `127.0.0.1:8786`
  and a Vite dev server on `127.0.0.1:5174` with
  `VITE_DEV_API_PROXY_TARGET=http://127.0.0.1:8786`, so the page used current
  code against the operator PostgreSQL data instead of the existing 8765 Docker
  API. Network requests returned 200 for `/api/bootstrap`,
  `/api/macro/modules/overview`, `/api/status`, and the macro series query.
  `/macro` rendered "今日决策台", source-backed Trade Map legs
  `BIL · 现金/短债 · 做多/防守`, `QQQ · 纳斯达克 · 回避/做空代理`, and
  `HYG · 高收益信用 · 低配`, plus event catalysts including `BEA GDP 发布`,
  `FOMC 决议`, and `10Y 国债拍卖 Bid/Cover`.
- The isolated browser QA DOM probe found no deleted route slugs
  (`crypto-derivatives`, `rates/auctions`, `fed/statements`, `fed/speeches`,
  `global-dollar`, `subsurface`, `economy/consumer`, `volatility/dashboard`,
  `credit/cds`) and no user-facing raw labels (`fed_corridor`, `cross_asset`,
  `positioning`, `未知宏观状态`) in the `/macro` page text. Direct navigation to
  `/macro/volatility/dashboard` rendered the ordinary route-error surface
  instead of a compatibility module shell. Console output had no app errors; the
  only warning was React Router's future-flag notice.
- Live Docker cadence QA found the existing `parallax-app-1` container was still
  running the pre-feature image: `macrodata-cli 0.1.8`, no `bundle_names`
  setting, and no importer JSON sanitizer. Its latest unattended
  `macro-core` steady run at `2026-06-16T08:14:17Z` failed with
  `ValueError: Out of range float values are not JSON compliant: nan`.
  Rebuilding with `docker compose up -d --build migrate app` installed
  `macrodata-cli 0.1.9` from pinned rev
  `c59b298994d111f36b4eef292790714057db42c0`, removed the stale
  `bundle_name` setting, and left PostgreSQL data intact. A subsequent
  container-side `parallax macro sync --bundle macro-core --start 2026-06-09
--end 2026-06-16` exited `ok=true`, with FRED configured via redacted
  settings and no NaN error.
- After the rebuilt app restarted, unattended `macro_sync` claimed all three
  configured steady windows from the real PostgreSQL queue. Latest DB audit:
  `macro-core` `2026-06-09..2026-06-16` completed at
  `2026-06-16T08:35:43Z` with 461 observations, 112 changed, 349 noop, FRED
  configured, no error; `macro-calendar-core` completed at
  `2026-06-16T08:35:47Z` with no observations for the empty current event
  window and no error; `treasury-auction-core` completed at
  `2026-06-16T08:35:55Z` with no observations for the empty current auction
  window and no error.
- Production-container browser smoke on `http://127.0.0.1:8765/macro` after
  rebuild rendered `今日决策台`, `资金面`, `跨资产确认`, event catalysts, and
  credit text; it did not leak deleted route slugs, did not show the old
  generic `重要变化 / 宏观 / RRP 缓冲偏低` label path, and browser console error
  count was 0.
- `make check-all` now passes SDD validation, all-active SDD gate checks, and generated-doc checks, then stops at repository-wide `ruff format --check` baseline files outside this macro slice. The failing files are unchanged non-macro backend/test files and remain covered by the global tech-debt row.

## Timsun Parity And Source Research — 2026-06-16

Benchmark pages checked:

- `https://timsun.net/`: first-screen decision console, top changes, confirmation/divergence, data quality, catalysts, watch triggers, and broad section inventory for assets/rates/Fed/liquidity/economy/volatility/credit.
- `https://timsun.net/trade-map`: five-asset radar (`NDX`, `BTC`, `GOLD`, `SPX`, `TLT`), deployed-capital/P&L framing, current action/rationale, risk temperature, historical trust, holding-period review, confirmation checklist, exit/risk events, and historical review table.
- `https://timsun.net/rates/yield-curve`: curve shape, 2s10s/3m10s/5s30s, current/1w/1m/3m curve comparison, spread history, nominal/real/breakeven tenor table, trade implications, invalidation, and time frame.

Live Parallax coverage audit:

- Redacted runtime paths confirmed again: `/Users/qinghuan/.parallax/config.yaml` and `/Users/qinghuan/.parallax/workers.yaml`; macrodata enabled; FRED configured through `FINANCE_FRED_API_KEY`.
- Before Task 31, `uv run parallax macro status` reported macrodata-cli `0.1.9`, required bundles `3/3` available, 81,508 observations, 150 concepts, latest snapshot `ready`, `facts_max_observed_at=2026-06-16`, and projection lag `0`. After Task 32, current live status reports macrodata-cli `0.1.11`, required bundles `4/4` available, 81,539 observations, 153 concepts, latest snapshot `ready`, `facts_max_observed_at=2026-06-16`, and projection lag `0`.
- Read-only current-code audit across the then-current 21 retained modules found every required concept present, every primary chart `ok`, and no module-view data-health gaps in the current snapshot before `rates/expectations` was removed. After the hard delete, a 2026-06-17 read-only audit checked the current 20 retained backend modules against the operator config and current PostgreSQL read models. The snapshot was `ready`, facts max observed date was `2026-06-16`, projection lag was `0`, and all 20 modules built through `build_macro_module_view(...)`. Optional/reference concept gaps now carry `scope=module_reference`, so live `assets/commodities` and `volatility/vix` render `部分可用` rather than misleading `缺失`; required concept error gaps still carry `scope=module_blocker` and keep affected modules missing. Overview global gaps now carry `scope=global_reference` when the persisted snapshot is `ready`, so the first-screen decision console reports `partial` data-quality watch instead of a false missing-page state. The live audit now reports no missing retained backend modules, 11 `ok` modules, and 9 `partial` modules. Rate-probability coverage stays a source-backed successor task.
- The current snapshot has the intended decision-console scenario keys: `confidence`, `current_regime`, `top_changes`, `confirmations`, `contradictions`, `trade_map`, `watch_triggers`, `invalidations`, and `quality_blockers`.

Source candidates classified for successor tasks:

- Fed text/speech/minutes: official Federal Reserve FOMC calendars, statements/minutes pages, monetary-policy RSS, and speeches RSS now back `fed-text-core`; the remaining successor work is hawk/dove delta scoring, speaker tagging, and route-quality read-model design.
- Treasury auctions: U.S. Treasury FiscalData and TreasuryDirect cover completed auction result facts; auction tail still requires a reliable when-issued yield source.
- Rate probabilities: CME FedWatch and FedWatch API are the correct source family, but automation should use an approved API/license path rather than scraping public pages. `rates/expectations` remains deleted until that source-backed lane exists.
- Volatility: Cboe public historical VIX/volatility-index downloads, Yahoo `^MOVE`, and term-structure pages cover some indices/proxies; this feature implements official Cboe VIX9D/VVIX/SKEW downloads, while VIX futures, options surface, open/close detail, and licensed ICE MOVE distribution likely require Cboe DataShop/LiveVol, ICE, Bloomberg, or another licensed feed.
- Credit: FINRA fixed-income/TRACE aggregate APIs can deepen credit liquidity; CDS remains a licensed-source gap.
- Liquidity: H.4.1/FRED/NY Fed/OFR cover balance sheet and funding rates/volumes; global-dollar and cross-currency basis need BIS lower-frequency statistics or paid Bloomberg/Refinitiv-style daily basis feeds.
- Assets/options: OCC and Cboe public reports can seed open-interest/volume research, while production GEX needs strike/expiry OI plus explicit calculation assumptions or a licensed specialist feed.
- Crypto derivatives: OKX and Deribit public APIs can seed OI/funding/basis/vol, while historical normalized depth may need Amberdata/Kaiko/Tardis approval.
- Economy: BEA schedule/API and FRED `GDPNOW`/Atlanta Fed GDPNow are public candidates; release surprise/consensus likely needs Bloomberg/Econoday/Trading Economics or another licensed calendar.

Product decision recorded in `plan.md`: do not restore deleted pages or add runtime future-source labels for these gaps. They become new modules only after source, read model, UI, and verification gates are implemented.

Documentation verification after adding the timsun parity audit:

- `uv run python scripts/validate_sdd_artifacts.py` -> pass.
- `uv run python scripts/regen_sdd_work_index.py` -> regenerated `docs/generated/sdd-work-index.md`.
- `uv run python scripts/regen_sdd_work_index.py --check` -> pass.
- `uv run pytest tests/architecture/test_sdd_artifact_validator.py -q` -> `119 passed`.
- `git diff --check` -> pass.

## Task 20 Verification — Trade Map Five-Asset Historical Review

Red tests:

- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_trade_map_adds_five_asset_historical_review -q` initially failed with `KeyError: 'historical_review'` because overview `decision_console.trade_map` only echoed scenario expressions/legs.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts -t "formats trade-map historical review" --run` initially failed because `MacroDecisionTradeMapItem.history` was `undefined`.
- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_module_view_labels_hy_oas_watch_and_invalidation_codes -q` initially failed because backend `_code_label` mapped `hy_oas_widening` and `hy_oas_tightens` to `待确认信号`.

Implementation notes:

- Overview `decision_console.trade_map` now receives a backend-generated `historical_review` for `NDX`, `BTC`, `GOLD`, `SPX`, and `TLT` using the projected macro observation rows already stored in PostgreSQL.
- `/api/macro/modules/overview` now loads the five Trade Map reliability concepts through `observations_for_concepts` with a 60-day bounded lookback. Non-overview modules still use latest observations only.
- React only formats and displays backend-provided review lines. It does not compute returns, win rates, or outcomes.
- Known HY OAS widening/tightening rules are now labeled in backend and frontend mappings, so the current overview does not show `待确认信号` for those rules.

Green tests and checks:

- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_trade_map_adds_five_asset_historical_review -q` -> pass.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts -t "formats trade-map historical review" --run` -> pass.
- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_module_view_labels_hy_oas_watch_and_invalidation_codes -q` -> pass.
- `uv run pytest tests/unit/test_api_macro_contract.py::test_macro_overview_module_api_loads_event_concepts_for_decision_console -q` -> pass; overview API uses `observations_for_concepts`, includes event concepts plus `asset:ndx`, `crypto:btc`, `asset:gld`, `asset:spx`, and `asset:tlt`, and returns a Trade Map `historical_review`.
- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py -q` -> `80 passed`.
- `uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py src/parallax/app/surfaces/api/routes_macro.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py` -> pass.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run` -> 2 files passed, 8 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run lint` -> ESLint passed and architecture tests 13 files passed, 73 tests passed.
- `cd web && npm run format:check` -> pass.

Browser smoke:

- Temporary current-code API: `127.0.0.1:8787`; temporary Vite dev server: `127.0.0.1:5175` with `VITE_DEV_API_PROXY_TARGET=http://127.0.0.1:8787`.
- Chrome DevTools DOM probe on `http://127.0.0.1:5175/macro` confirmed `五资产 60日验证`, `NDX 纳斯达克`, `BTC 比特币`, `GOLD 黄金`, `SPX 标普500`, and `TLT 长债` render inside `交易映射`.
- The same DOM probe confirmed `待确认信号` was absent after adding HY OAS labels, while `HY OAS 5日走阔` and `HY OAS 收窄` were present.
- Screenshot saved at `/tmp/parallax-qa/macro-trade-map-history.png`.
- Dev-smoke console still showed transient local `/ws` 401/502 noise from the temporary Vite/API proxy and API restart; this was not counted as zero-console production evidence.

## Task 21 Verification — Trade Map Paper P&L And Checklist

Red tests:

- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_trade_map_adds_five_asset_historical_review -q` initially failed with `KeyError: 'portfolio_review'` because overview `decision_console.trade_map` only had `historical_review`.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts -t "formats trade-map historical review" --run` initially failed because `MacroDecisionTradeMapItem.portfolio` was `undefined`.

Implementation notes:

- Overview `decision_console.trade_map` now derives `portfolio_review` from the five-asset historical rows using a deterministic `$10,000` equal-weight paper map.
- Direction-adjusted paper P&L, P&L percentage, max adverse dollars, risk temperature, and summary are generated in Python from persisted macro observation history.
- `action_checklist` is generated from backend `confirms_on` and `invalidates_on` labels plus a `position_review` row; React only formats these backend rows.
- Macro Workbench renders paper map and action checklist inside the existing Trade Map section using owner CSS under `web/src/features/macro/ui/workbench/macroWorkbench.css`.

Green tests and checks:

- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_trade_map_adds_five_asset_historical_review -q` -> pass.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts -t "formats trade-map historical review" --run` -> pass.
- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py -q` -> `80 passed`.
- `uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py src/parallax/app/surfaces/api/routes_macro.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py` -> pass.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run` -> 2 files passed, 8 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run test:architecture` -> 13 files passed, 73 tests passed.
- `cd web && npm run lint` -> ESLint passed and architecture tests 13 files passed, 73 tests passed.
- `cd web && npm run format:check` -> pass.

Browser smoke:

- Temporary current-code API: `127.0.0.1:8787`; temporary Vite dev server: `127.0.0.1:5175` with `VITE_DEV_API_PROXY_TARGET=http://127.0.0.1:8787`.
- Chrome DevTools DOM probe on `http://127.0.0.1:5175/macro` confirmed `$10K 纸面映射`, `P&L`, `纸面仓位复盘`, and `观察 HY OAS 5日走阔 是否继续确认。` render inside `交易映射`.
- The same DOM probe confirmed `待确认信号` was absent. Live data produced `$10,000 · P&L -$344 · 胜率 1/5 · 风险温度 高`, proving the displayed value came from current persisted history rather than fixture text.
- Desktop screenshot saved at `/tmp/parallax-qa/macro-trade-map-paper-pnl.png`.
- Mobile viewport probe confirmed the paper map and checklist remained visible and the Trade Map section had no horizontal overflow; screenshot saved at `/tmp/parallax-qa/macro-trade-map-paper-pnl-mobile.png`.
- Browser console showed only Vite connection logs, React DevTools guidance, and the existing React Router future-flag warning. Key network requests `/api/bootstrap`, `/api/macro/modules/overview`, `/api/status`, and `/api/macro/series?...` returned 200.
- The temporary API process logged existing GMGN raw-frame duplicate-key disconnect/reconnect noise during smoke startup; this was not caused by the macro Trade Map display change and remains outside this task's scope.
- Temporary services were stopped; `lsof -nP -iTCP:8787 -sTCP:LISTEN` and `lsof -nP -iTCP:5175 -sTCP:LISTEN` returned no listeners.

## Task 22 Verification — Trade Map Historical Trust And Holding-Period Review

Red tests:

- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_trade_map_adds_five_asset_historical_review -q` initially failed with `KeyError: 'historical_trust'` because overview `decision_console.trade_map` had no trust or holding-period fields.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts -t "formats trade-map historical review" --run` initially failed because `MacroDecisionTradeMapItem.trust` was `undefined`.

Implementation notes:

- Overview `decision_console.trade_map` now emits `historical_trust` and `holding_period_review` whenever the five-asset historical review is available.
- The backend evaluates 1D, 5D, and 20D holding periods from persisted macro observation rows. For each horizon it uses the first observation at or after the horizon date, so daily series with weekends/holidays still produce deterministic rows.
- Historical trust is computed from all evaluated holding-period samples, with score percentage, quality bucket, hit count, sample count, and a display summary.
- React renders backend-provided trust and holding-period lines only; it does not compute returns, P&L, or trust scores locally.

Green tests and checks:

- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_trade_map_adds_five_asset_historical_review -q` -> pass.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts -t "formats trade-map historical review" --run` -> pass.
- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py -q` -> `80 passed`.
- `uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py src/parallax/app/surfaces/api/routes_macro.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py` -> pass.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run` -> 2 files passed, 8 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run test:architecture` -> 13 files passed, 73 tests passed.
- `cd web && npm run lint` -> ESLint passed and architecture tests 13 files passed, 73 tests passed.
- `cd web && npm run format:check` -> pass after formatting `web/tests/component/features/macro/MacroModulePages.test.tsx`.

Browser smoke:

- Temporary current-code API: `127.0.0.1:8787`; temporary Vite dev server: `127.0.0.1:5175` with `VITE_DEV_API_PROXY_TARGET=http://127.0.0.1:8787`.
- Chrome DevTools DOM probe on `http://127.0.0.1:5175/macro` confirmed `历史可信度`, 1D/5D/20D holding-period rows, and no `待确认信号` inside `交易映射`.
- Live data produced `历史可信度 20.0% · 低 · 15 个样本`, `1D 已完成 · 3/5 · P&L +$30 · 均值 +0.30%`, `5D 已完成 · 0/5 · P&L -$107 · 均值 -1.07%`, and `20D 已完成 · 0/5 · P&L -$365 · 均值 -3.65%`.
- Desktop screenshot saved at `/tmp/parallax-qa/macro-trade-map-trust-holding.png`.
- Mobile viewport probe confirmed trust and 20D holding rows remained visible and the Trade Map section had no horizontal overflow; screenshot saved at `/tmp/parallax-qa/macro-trade-map-trust-holding-mobile.png`.
- Browser console showed only Vite connection logs, React DevTools guidance, and the existing React Router future-flag warning. Key network requests `/api/bootstrap`, `/api/macro/modules/overview`, `/api/status`, and `/api/macro/series?...` returned 200.
- Temporary services were stopped; `lsof -nP -iTCP:8787 -sTCP:LISTEN` and `lsof -nP -iTCP:5175 -sTCP:LISTEN` returned no listeners.

## Task 23 Verification — Yield Curve Curve-Diagnostics Workbench

Red tests:

- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_yield_curve_module_read_adds_curve_diagnostics_from_history -q` initially failed with `KeyError: 'curve_diagnostics'` because `rates/yield-curve` module reads only emitted generic module text.
- `cd web && npm run test -- tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts tests/component/features/macro/MacroRatesWorkbench.test.tsx --run` initially failed because `RatesWorkbenchView.curveDiagnostics` was `undefined` and the page had no `曲线诊断` region.

Implementation notes:

- `rates/yield-curve` now emits backend `curve_diagnostics` when persisted Treasury histories can support it.
- The backend calculates 2s10s, 3m10y, and 5s30s current spreads plus 1w/1m/3m changes from module feature histories, then classifies shape and emits implication/invalidation text.
- The frontend renders this backend payload after the primary rates chart in `RatesCurveDiagnostics`; React only formats backend fields and does not compute spreads.
- Curve diagnostics CSS lives in adjacent owner CSS `web/src/features/macro/ui/rates/ratesCurveDiagnostics.css` so `macroRatesWorkbench.css` remains under the 500-line architecture budget.

Green tests and checks:

- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_yield_curve_module_read_adds_curve_diagnostics_from_history -q` -> pass.
- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py -q` -> `81 passed`.
- `uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py` -> pass.
- `cd web && npm run test -- tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts tests/component/features/macro/MacroRatesWorkbench.test.tsx --run` -> 2 files passed, 21 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run lint` -> ESLint passed and architecture tests 13 files passed, 73 tests passed.
- `cd web && npm run format:check` -> pass.

Live data probe:

- Temporary current-code API: `127.0.0.1:8787`; temporary Vite dev server: `127.0.0.1:5175` with `VITE_DEV_API_PROXY_TARGET=http://127.0.0.1:8787`.
- `curl -I http://127.0.0.1:5175/macro/rates/yield-curve` returned `HTTP/1.1 200 OK`.
- A direct repository/view-builder probe against the same current PostgreSQL data path used by `/api/macro/modules/{module_id}` returned snapshot `ready`, as-of `2026-06-16`, shape `牛陡`, and rows: `2s10s` current `39bp` with 1w `+1bp`, 1m `-9bp`, 3m `-16bp`; `3m10y` current `70bp` with 1w `-7bp`, 1m `-7bp`, 3m `+14bp`; `5s30s` current `76bp` with 1w `+4bp`, 1m `-15bp`, 3m `-27bp`.
- The live diagnostics summary was `曲线牛陡：10Y 下行且 2s10s 走陡，增长下行压力高于期限溢价。`; implication was `增长压力：优先检查信用利差、盈利预期和防守资产确认。`; invalidation was `若 10Y 重新上行且信用未恶化，增长压力读法降级。`.
- The live `curve_diagnostics` JSON contained no raw `rates:dgs` keys in user-facing diagnostics.
- Browser screenshot automation could not complete in this environment: Playwright MCP, Node REPL Playwright with bundled Chromium, Node REPL Playwright with system Chrome headless, and Node REPL Playwright with system Chrome visible each failed before navigation because Chrome launched and then exited with `SIGKILL` / `Target page, context or browser has been closed`. No screenshot file was produced for this task. The component tests above still verify the DOM region and text; the live probe verifies current backend payload.
- The temporary API process logged the existing GMGN raw-frame duplicate-key reconnect noise during smoke startup, matching prior Task 21/22 observations. The Vite process logged early proxy connection-refused messages before the API finished starting and the existing React Router future-flag warning.
- Temporary services were stopped; `lsof -nP -iTCP:8787 -sTCP:LISTEN` and `lsof -nP -iTCP:5175 -sTCP:LISTEN` returned no listeners.

## Task 24 Verification — Credit Stress Diagnostics Workbench

Red tests:

- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_credit_stress_module_read_adds_credit_diagnostics_from_history -q` initially failed with `KeyError: 'credit_diagnostics'` because `credit/stress` module reads only emitted generic module text.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run` initially failed because `buildMacroCreditDiagnostics` did not exist and the leaf module page had no `信用压力诊断` region.

Implementation notes:

- `credit/stress` now emits backend `credit_diagnostics` when persisted credit histories can support it.
- The backend calculates HY OAS, IG OAS, CCC-HY tail spread, and SLOOS large-firm tightening current values plus 1w/1m/3m or 1q changes from module feature histories, then classifies credit regime and emits implication/invalidation text.
- The frontend renders this backend payload between `主市场证据` and `驱动与反证` in the generic leaf module page. React only formats backend fields and does not compute credit changes.
- Credit diagnostics now share the generic `MacroSignalDiagnosticsPanel` and `macroSignalDiagnostics.css` with volatility/liquidity diagnostics. The old credit-specific panel/CSS were deleted in Task 26 rather than kept as compatibility wrappers.

Green tests and checks:

- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_credit_stress_module_read_adds_credit_diagnostics_from_history -q` -> pass.
- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py -q` -> `82 passed`.
- `uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py` -> pass.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run` -> 2 files passed, 10 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run lint` -> ESLint passed and architecture tests 13 files passed, 73 tests passed after replacing off-contract `960px`/`620px` media queries with approved breakpoints.
- `cd web && npm run format:check` -> pass after formatting `web/src/features/macro/model/macroWorkbenchModel.ts` and `web/tests/unit/features/macro/model/macroWorkbenchModel.test.ts`.

Live data probe:

- A direct repository/view-builder probe against the same current PostgreSQL data path used by `/api/macro/modules/{module_id}` returned snapshot `ready`, as-of `2026-06-16`, regime `压力可控`, and summary `信用压力可控：利差和银行信贷暂未给出强方向，等待尾部确认。`.
- Live rows: `HY OAS` current `271bp` with 1w `-5bp`, 1m `-11bp`, 3m `-57bp`; `IG OAS` current `74bp` with 1w `0bp`, 1m `-2bp`, 3m `-19bp`; `CCC-HY 尾部` current `677bp` with 1w `+1bp`, 1m `+28bp`, 3m `+27bp`; `SLOOS 大中型收紧` current `8.1%` with 1q `+2.8%`.
- The live diagnostics implication was `信用暂未给强方向：等待 HY OAS、CCC-HY 尾部和 SLOOS 同向确认。`; invalidation was `若 HY OAS 或 CCC-HY 尾部单周走阔超过 25bp，重新评估信用压力。`.
- The live `credit_diagnostics` JSON contained no raw `credit:` keys in user-facing diagnostics.

Browser smoke:

- Temporary current-code API: `127.0.0.1:8787`; temporary Vite dev server: `127.0.0.1:5175` with `VITE_DEV_API_PROXY_TARGET=http://127.0.0.1:8787`.
- Desktop Playwright probe on `http://127.0.0.1:5175/macro/credit/stress` confirmed `信用压力诊断 · 压力可控`, `HY OAS`, `CCC-HY 尾部`, and `SLOOS 大中型收紧` render from live data; the diagnostics region did not contain `credit:` and the page had no horizontal overflow.
- Desktop screenshot saved at `/tmp/parallax-qa/macro-credit-stress-diagnostics.png`.
- Mobile viewport probe at `390x844` confirmed the same diagnostics title, HY OAS and SLOOS values, and no horizontal overflow; screenshot saved at `/tmp/parallax-qa/macro-credit-stress-diagnostics-mobile.png`.
- Browser console showed only Vite connection logs, React DevTools guidance, and the existing React Router future-flag warning. Key network requests `/api/bootstrap`, `/api/macro/modules/credit/stress`, `/api/macro/series?...`, and `/api/status` returned 200.
- The temporary API process logged the existing GMGN raw-frame duplicate-key reconnect noise during smoke startup, matching prior Task 21/22 observations and unrelated to the macro credit diagnostics change.
- Temporary services were stopped; `lsof -nP -iTCP:8787 -sTCP:LISTEN` and `lsof -nP -iTCP:5175 -sTCP:LISTEN` returned no listeners.

## Task 25 Verification — Volatility VIX Diagnostics Workbench

Red tests:

- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_volatility_vix_module_read_adds_volatility_diagnostics_from_history -q` initially failed with `KeyError: 'volatility_diagnostics'` because `volatility/vix` module reads only emitted generic module text.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run` initially failed because `buildMacroVolatilityDiagnostics` did not exist and the leaf module page had no `波动率诊断` region.

Implementation notes:

- `volatility/vix` now emits backend `volatility_diagnostics` when persisted volatility histories can support it.
- The backend calculates VIX spot, VIX3M-VIX term premium, VIXY/VIXM front-end pressure, and VXN current values plus 1w/1m changes from module feature histories, then classifies volatility regime and emits implication/invalidation text.
- The frontend renders this backend payload between `主市场证据` and `驱动与反证` in the generic leaf module page. React only formats backend fields and does not compute volatility, term premium, or ETF-relative changes.
- Volatility diagnostics now share the generic `MacroSignalDiagnosticsPanel` and `macroSignalDiagnostics.css` with credit/liquidity diagnostics. The old volatility-specific panel/CSS were deleted in Task 26 rather than kept as compatibility wrappers.
- Timsun benchmark note: `https://timsun.net/` frames volatility as VIX spot plus term structure/contango, VIXD, MOVE, NFCI, and backwardation triggers. This task intentionally shipped only source-backed Parallax fields available at the time; later continuations add the source-backed Yahoo `^MOVE` proxy and official Cboe VIX9D/VVIX/SKEW, while real futures/options term structure, realized volatility, and licensed volatility feeds remain documented source gaps.

Green tests and checks:

- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_volatility_vix_module_read_adds_volatility_diagnostics_from_history -q` -> pass.
- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py -q` -> `83 passed`.
- `uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py` -> pass.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run` -> 2 files passed, 12 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run lint` -> ESLint passed and architecture tests 13 files passed, 73 tests passed.
- `cd web && npm run format:check` -> pass after formatting `web/tests/component/features/macro/MacroModulePages.test.tsx` and `web/tests/unit/features/macro/model/macroWorkbenchModel.test.ts`.

Live data probe:

- A direct repository/view-builder probe against the same current PostgreSQL data path used by `/api/macro/modules/{module_id}` returned snapshot `ready`, as-of `2026-06-16`, regime `中性`, and summary `波动率信号中性：等待 VIX 现货、期限结构和期货代理同向确认。`.
- Live rows: `VIX 现货` current `17.7` with 1w `-3.8`, 1m `-0.2`; `VIX3M-VIX 期限溢价` current `2.8pts` with 1w `+2.5pts`, 1m `-0.5pts`; `VIXY/VIXM 前端压力` current `1.53x` with 1w `-2.9%`, 1m `-10.03%`; `VXN 纳指波动率` current `27.3` with 1w `-3.2`, 1m `+2.7`.
- The live diagnostics implication was `波动率暂未给强方向：等待 VIX、VIX3M-VIX 与 VIXY/VIXM 同向确认。`; invalidation was `若 VIX 单周上行超过 5 点或期限结构转负，重新评估波动率压力。`.
- The live `volatility_diagnostics` JSON contained no raw `vol:` keys in user-facing diagnostics.

Browser smoke:

- Temporary current-code API: `127.0.0.1:8787`; temporary Vite dev server: `127.0.0.1:5175` with `VITE_DEV_API_PROXY_TARGET=http://127.0.0.1:8787`.
- Desktop Playwright probe on `http://127.0.0.1:5175/macro/volatility/vix` confirmed `波动率诊断 · 中性`, `VIX 现货`, `VIX3M-VIX 期限溢价`, `VIXY/VIXM 前端压力`, and `VXN 纳指波动率` render from live data; the page did not contain `vol:` and had no horizontal overflow.
- Desktop screenshot saved at `/tmp/parallax-qa/macro-volatility-diagnostics.png`.
- Mobile viewport probe at `390x844` confirmed the same diagnostics title and rows, no raw `vol:` key, and no horizontal overflow; screenshot saved at `/tmp/parallax-qa/macro-volatility-diagnostics-mobile.png`.
- Browser console had no page errors, no console errors, and no 4xx/5xx responses for the checked API/page requests. The Vite terminal still logged the existing React Router future-flag warning.
- The temporary API process logged existing GMGN raw-frame duplicate-key reconnect noise during smoke startup, matching prior Task 21/22/24 observations and unrelated to the macro volatility diagnostics change.
- Temporary services were stopped; `lsof -nP -iTCP:8787 -sTCP:LISTEN` and `lsof -nP -iTCP:5175 -sTCP:LISTEN` returned no listeners.

## Task 26 Verification — Liquidity RRP/TGA Diagnostics Workbench

Red tests:

- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_liquidity_rrp_tga_module_read_adds_liquidity_diagnostics_from_history -q` initially failed with `KeyError: 'liquidity_diagnostics'` after the test fixture labels were extended for liquidity concepts.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run` initially failed because `buildMacroLiquidityDiagnostics` did not exist and the leaf module page had no `流动性诊断` region.

Implementation notes:

- `liquidity/rrp-tga` now emits backend `liquidity_diagnostics` when persisted liquidity histories can support it.
- The backend calculates SOFR-IORB corridor pressure, RRP buffer, TGA fiscal cash, and net liquidity current values plus 1w/1m changes from module feature histories, then classifies liquidity regime and emits implication/invalidation text.
- Source values remain in their persisted units; the backend converts million-dollar liquidity balances into B/T display fields and rate spreads into bp fields before the payload reaches React.
- The frontend renders this backend payload between `主市场证据` and `驱动与反证` in the generic leaf module page. React only formats backend fields and does not compute SOFR-IORB, RRP/TGA changes, or net liquidity.
- The duplicated `MacroCreditDiagnosticsPanel` / `MacroVolatilityDiagnosticsPanel` and their separate CSS files were deleted. Credit, volatility, and liquidity now share `MacroSignalDiagnosticsPanel` plus adjacent owner CSS `macroSignalDiagnostics.css`.
- Timsun benchmark note: `https://timsun.net/liquidity/rrp-tga` frames liquidity around RRP/TGA/net-liquidity conditions, SOFR-IORB pressure alerts, and future event heatmaps. This task intentionally ships only source-backed current/history Parallax fields and leaves future 7d/14d liquidity heatmaps as a separate event-model gap.

Green tests and checks:

- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_liquidity_rrp_tga_module_read_adds_liquidity_diagnostics_from_history -q` -> pass.
- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py -q` -> `84 passed`.
- `uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py` -> pass.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run` -> 2 files passed, 14 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run lint` -> ESLint passed and architecture tests 13 files passed, 73 tests passed.
- `cd web && npm run format:check` -> pass after formatting `web/tests/component/features/macro/MacroModulePages.test.tsx` and `web/tests/fixtures/macroFixture.ts`.

Live data probe:

- A direct repository/view-builder probe against the same current PostgreSQL data path used by `/api/macro/modules/{module_id}` returned snapshot `ready`, as-of `2026-06-16`, regime `净注入`, and summary `净流动性回升：资金面给风险资产提供边际支持，但仍需信用和波动率确认。`.
- Live rows: `SOFR-IORB 走廊压力` current `0bp` with 1w `+2bp`, 1m `+6bp`; `RRP 缓冲` current `0B` with 1w `0B`, 1m `0B`; `TGA 财政现金` current `816B` with 1w `-9.5B`, 1m `+8.6B`; `净流动性` current `5.92T` with 1w `+58.5B`, 1m `+69.4B`.
- The live diagnostics implication was `净注入：risk-on 可以获得资金面确认，但需要波动率和信用不背离。`; invalidation was `若净流动性重新转负或 SOFR-IORB 走阔，净注入读法失效。`.
- The live `liquidity_diagnostics` JSON contained no raw `liquidity:` keys in user-facing diagnostics.

Browser smoke:

- Temporary current-code API: `127.0.0.1:8787`; temporary Vite dev server: `127.0.0.1:5175` with `VITE_DEV_API_PROXY_TARGET=http://127.0.0.1:8787`.
- `curl -I http://127.0.0.1:5175/macro/liquidity/rrp-tga` returned `HTTP/1.1 200 OK`.
- Browser screenshot automation could not complete in this environment: Node REPL Playwright with system Chrome headless, Chrome channel, system Chrome headed, and bundled Chromium each failed before navigation because Chrome launched and then exited with `SIGKILL` / `Target page, context or browser has been closed`, or bundled Chromium was not installed. No screenshot file was produced for this task.
- Component tests verify the `流动性诊断` DOM region order and text with no raw `liquidity:` keys; the live probe verifies the current backend payload.
- The temporary API process logged the existing GMGN raw-frame duplicate-key reconnect noise during smoke startup, matching prior Task 21/22/24/25 observations and unrelated to the macro liquidity diagnostics change.
- Temporary services were stopped; `lsof -nP -iTCP:8787 -sTCP:LISTEN` and `lsof -nP -iTCP:5175 -sTCP:LISTEN` returned no listeners.

## Task 27 Verification — Inflation Diagnostics Workbench

Red tests:

- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_inflation_module_read_adds_inflation_diagnostics_from_history -q` initially failed with `KeyError: 'inflation_diagnostics'` because `economy/inflation` module reads only emitted generic module text.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run` initially failed because `buildMacroInflationDiagnostics` did not exist and the leaf module page had no `通胀诊断` region.

Implementation notes:

- `economy/inflation` now emits backend `inflation_diagnostics` when persisted inflation histories can support it.
- The backend calculates CPI YoY, Core CPI YoY, PPI YoY, and 10Y breakeven current/change rows from module feature histories, then classifies inflation regime and emits implication/invalidation text.
- Year-over-year inflation and breakeven bp changes are computed in Python from persisted macro observation histories. React only formats backend fields and does not compute YoY inflation, breakeven changes, surprise, or consensus deltas.
- The diagnostics render through the generic `MacroSignalDiagnosticsPanel` between `主市场证据` and `驱动与反证`.
- Timsun benchmark note: `https://timsun.net/` exposes economy/inflation as part of the macro decision surface. This task intentionally ships only source-backed CPI/PPI/breakeven diagnostics and leaves actual-vs-consensus, revisions, and surprise history as source gaps.

Green tests and checks:

- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_inflation_module_read_adds_inflation_diagnostics_from_history -q` -> pass.
- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py -q` -> `85 passed`.
- `uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py` -> pass after splitting one long line.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run` -> 2 files passed, 16 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run lint` -> ESLint passed and architecture tests 13 files passed, 73 tests passed.
- `cd web && npm run format:check` -> pass after formatting `web/tests/component/features/macro/MacroModulePages.test.tsx` and `web/tests/fixtures/macroFixture.ts`.

Live data probe:

- A direct repository/view-builder probe against the same current PostgreSQL data path used by `/api/macro/modules/{module_id}` returned snapshot `ready`, as-of `2026-06-16`, regime `中性`, and summary `通胀信号中性：等待 CPI、PCE 与通胀补偿同向确认。`.
- Live rows: `CPI 同比` current `4.17%` with 1m `+0.39pp`; `核心 CPI 同比` current `2.82%` with 1m `+0.08pp`; `PPI 同比` current `13.08%` with 1m `+3.67pp`; `10Y 通胀补偿` current `2.32%` with 1w `-3bp`, 1m `-17bp`.
- The live diagnostics implication was `通胀暂未给强方向：等待 CPI/Core PCE 与 breakeven 同向确认。`; invalidation was `若核心通胀或 breakeven 1m 明显上行，重新评估通胀压力。`.
- The live `inflation_diagnostics` JSON contained no raw `inflation:` keys in user-facing diagnostics.

Browser smoke:

- Temporary current-code API: `127.0.0.1:8787`; temporary Vite dev server: `127.0.0.1:5175` with `VITE_DEV_API_PROXY_TARGET=http://127.0.0.1:8787`.
- `curl -I http://127.0.0.1:5175/macro/economy/inflation` returned `HTTP/1.1 200 OK`.
- Browser screenshot automation could not complete in this environment: Node REPL Playwright with system Chrome headless failed before navigation because Chrome launched and then exited with `SIGKILL` / `Target page, context or browser has been closed`. No screenshot file was produced for this task.
- Component tests verify the `通胀诊断` DOM region order and text with no raw `inflation:` keys; the live probe verifies the current backend payload.
- The temporary API process logged the existing GMGN raw-frame duplicate-key reconnect noise during smoke startup, matching prior Task 21/22/24/25/26 observations and unrelated to the macro inflation diagnostics change.
- Temporary services were stopped; `lsof -nP -iTCP:8787 -sTCP:LISTEN` and `lsof -nP -iTCP:5175 -sTCP:LISTEN` returned no listeners.

## Task 28 Verification — Employment Diagnostics Workbench

Red tests:

- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_employment_module_read_adds_employment_diagnostics_from_history -q` first exposed a missing labor label in the test helper; after fixing the helper fixture labels, it failed with `KeyError: 'employment_diagnostics'` because `economy/employment` module reads only emitted generic module text.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run` initially failed because `buildMacroEmploymentDiagnostics` did not exist and the leaf module page had no `就业诊断` region.

Implementation notes:

- `economy/employment` now emits backend `employment_diagnostics` when persisted labor histories can support it.
- The backend calculates unemployment-rate change, payroll monthly gain/deceleration, initial-claims change, job-openings change, and average-hourly-earnings YoY from module feature histories, then classifies labor regime and emits implication/invalidation text.
- Payroll and claims unit normalization stays in Python before the payload reaches React. A live probe caught an initial-claims small-change edge case where `4,000` persons could display as `4000k`; the implementation now compares converted current/prior values and the unit test fixture protects a `+4k` weekly change.
- The frontend renders this backend payload between `主市场证据` and `驱动与反证` in the generic leaf module page. React only formats backend fields and does not compute payroll changes, claims changes, wage YoY, surprise, consensus, or revisions.
- Timsun benchmark note: `https://timsun.net/` treats labor data as part of the macro decision surface. This task intentionally ships only source-backed labor-history diagnostics and leaves actual-vs-consensus, revisions, and release surprise as source gaps.

Green tests and checks:

- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_employment_module_read_adds_employment_diagnostics_from_history -q` -> pass.
- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py -q` -> `86 passed`.
- `uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py` -> pass.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run` -> 2 files passed, 18 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run lint` -> ESLint passed and architecture tests 13 files passed, 73 tests passed.
- `cd web && npm run format:check` -> pass.
- `uv run pytest tests/architecture/test_macro_no_compatibility_contract.py -q` -> 13 passed.

Live data probe:

- `uv run parallax config` confirmed `config_path=/Users/qinghuan/.parallax/config.yaml`, `workers_config_path=/Users/qinghuan/.parallax/workers.yaml`, macrodata enabled, and FRED API key configured by env boolean; no secret values were copied into this verification.
- A direct repository/view-builder probe against the same current PostgreSQL data path used by `/api/macro/modules/{module_id}` returned snapshot `ready`, as-of `2026-06-16`, projection lag `0`, regime `中性`, and summary `就业信号中性：等待非农、失业率、初请和工资同向确认。`.
- Live rows: `失业率` current `4.3%` with 1m `0pp`; `非农新增` current `172k` with 1m `-7k`; `初请失业金` current `229k` with 1w `+4k`, 1m `+30k`; `职位空缺` current `7.62M` with 1m `+0.73M`; `平均时薪同比` current `3.45%` with 1m `-0.12pp`.
- The live diagnostics implication was `就业暂未给强方向：等待非农、初请、失业率和工资同向确认。`; invalidation was `若非农、失业率或初请出现单月明显反向变化，重新评估就业读法。`.
- The live `employment_diagnostics` JSON contained no raw `labor:` keys in user-facing diagnostics.

Browser smoke:

- Temporary current-code API: `127.0.0.1:8787`; temporary Vite dev server: `127.0.0.1:5175` with `VITE_DEV_API_PROXY_TARGET=http://127.0.0.1:8787`.
- `curl -I http://127.0.0.1:5175/macro/economy/employment` returned `HTTP/1.1 200 OK`.
- Desktop Playwright MCP probe on `http://127.0.0.1:5175/macro/economy/employment` confirmed `就业诊断 · 中性`, `失业率`, `非农新增`, `初请失业金`, `职位空缺`, and `平均时薪同比` render from live data. The page loaded with 0 console errors and 1 existing React Router future-flag warning.
- Mobile Playwright MCP probe at `390x844` confirmed the same diagnostics title and rows stack in a single column without text overlap; the page had 0 console errors and 1 existing React Router future-flag warning.
- Direct unauthenticated curl to `/api/macro/modules/economy/employment` returned `unauthorized`, as expected for a protected API. The browser session used the app bootstrap/auth path and the API logs showed `/api/macro/modules/economy/employment` and its series query returning `200 OK`.
- The temporary API process logged existing GMGN direct-WS duplicate raw-frame and invalid-url reconnect noise during smoke startup, matching prior macro tasks and unrelated to the employment diagnostics change.
- Temporary services were stopped; `lsof -nP -iTCP:8787 -sTCP:LISTEN` and `lsof -nP -iTCP:5175 -sTCP:LISTEN` returned no listeners.

## Task 29 Verification — GDP Growth Diagnostics Workbench

Red tests:

- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_gdp_module_read_adds_growth_diagnostics_from_history -q` initially failed with `KeyError: 'growth_diagnostics'` because `economy/gdp` module reads only emitted generic module text.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run` initially failed because `buildMacroGrowthDiagnostics` did not exist and the leaf module page had no `增长诊断` region.

Implementation notes:

- `economy/gdp` now emits backend `growth_diagnostics` when persisted growth histories can support it.
- The backend calculates real GDP YoY and quarter deceleration, industrial-production YoY/current change, housing-starts level/change, real PCE YoY/current change, and retail-sales YoY/current change from module feature histories, then classifies the growth regime and emits implication/invalidation text.
- Housing-starts unit normalization stays in Python before the payload reaches React. React only formats backend fields and does not compute GDP YoY, GDPNow, consumption changes, surprise, consensus, or revisions.
- The frontend renders this backend payload between `主市场证据` and `驱动与反证` in the generic leaf module page.
- Timsun benchmark note: `https://timsun.net/` treats GDP/growth as part of the macro decision surface. This task initially shipped source-backed GDP, production, housing, real PCE, and retail-sales history diagnostics; the later GDPNow continuation adds the source-backed nowcast row, leaving actual-vs-consensus, revisions, and surprise history as source gaps.

Green tests and checks:

- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_gdp_module_read_adds_growth_diagnostics_from_history -q` -> pass.
- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py -q` -> `87 passed`.
- `uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py` -> pass.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run` -> 2 files passed, 20 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run lint` -> ESLint passed and architecture tests 13 files passed, 73 tests passed.
- `cd web && npm run format:check` -> pass after formatting `web/src/features/macro/model/macroWorkbenchModel.ts` and `web/tests/component/features/macro/MacroModulePages.test.tsx`.
- `uv run pytest tests/architecture/test_macro_no_compatibility_contract.py -q` -> 13 passed.

Live data probe:

- `uv run parallax config` confirmed `config_path=/Users/qinghuan/.parallax/config.yaml`, `workers_config_path=/Users/qinghuan/.parallax/workers.yaml`, macrodata enabled, and FRED API key configured by env boolean; no secret values were copied into this verification.
- A direct repository/view-builder probe against the same current PostgreSQL data path used by `/api/macro/modules/{module_id}` returned snapshot `ready`, as-of `2026-06-16`, projection lag `0`, regime `增长韧性`, and summary `增长仍有韧性：实际 GDP 和消费维持扩张，风险资产盈利预期暂获支撑。`.
- Live rows: `实际 GDP 同比` current `2.57%` with 1q `+0.58pp`; `工业生产同比` current `1.67%` with 1m `+0.3pp`; `住房开工` current `1.47M` with 1m `-42k`; `实际 PCE 同比` current `2.1%` with 1m `-0.03pp`; `零售销售同比` current `4.87%` with 1m `+0.72pp`.
- The live diagnostics implication was `增长韧性：风险资产盈利端仍有支撑，但若通胀粘性同步存在，降息预期需降级。`; invalidation was `若实际 GDP 同比跌破 2% 且工业生产转负，增长韧性读法失效。`.
- The live `growth_diagnostics` JSON contained no raw `economy:` or `consumer:` keys in user-facing diagnostics.

Browser smoke:

- Temporary current-code API: `127.0.0.1:8787`; temporary Vite dev server: `127.0.0.1:5175` with `VITE_DEV_API_PROXY_TARGET=http://127.0.0.1:8787`.
- `curl -I http://127.0.0.1:5175/macro/economy/gdp` returned `HTTP/1.1 200 OK`.
- Desktop Playwright MCP probe on `http://127.0.0.1:5175/macro/economy/gdp` confirmed `增长诊断 · 增长韧性`, `实际 GDP 同比`, `工业生产同比`, `住房开工`, `实际 PCE 同比`, and `零售销售同比` render from live data. The page loaded with 0 console errors and 1 existing React Router future-flag warning.
- Mobile Playwright MCP probe at `390x844` confirmed the same diagnostics title and rows stack in a single column without text overlap; the page had 0 console errors and 1 existing React Router future-flag warning.
- The temporary API process logged existing GMGN direct-WS invalid-url reconnect noise and OKX/GMGN connection-state chatter during smoke shutdown, matching prior macro tasks and unrelated to the growth diagnostics change.
- Temporary services were stopped; `lsof -nP -iTCP:8787 -sTCP:LISTEN` and `lsof -nP -iTCP:5175 -sTCP:LISTEN` returned no listeners.

## Task 30 Verification — Fed Funds Corridor Diagnostics Workbench

Red tests:

- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_fed_funds_module_read_adds_policy_diagnostics_from_history -q` initially failed with `KeyError: 'policy_diagnostics'` because `rates/fed-funds` module reads only emitted generic module text.
- `cd web && npm run test -- tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts tests/component/features/macro/MacroRatesWorkbench.test.tsx --run` initially failed because `buildRatesWorkbenchView` did not expose `policyDiagnostics` and the rates workbench had no `政策走廊诊断` region.

Implementation notes:

- `rates/fed-funds` now emits backend `policy_diagnostics` when persisted policy-rate histories can support it.
- The backend calculates target range width, EFFR position versus target upper, EFFR-IORB, SOFR-EFFR, SOFR 30D-EFFR, and DFF-EFFR from module feature histories, then classifies policy-corridor regime and emits implication/invalidation text.
- Policy-rate and spread math stays in Python before the payload reaches React. React only formats backend fields and does not compute policy spreads, FedWatch probabilities, meeting probabilities, text deltas, or source-derived surprises.
- The frontend renders this backend payload between `利率主图` and `决策支持` in the rates workbench through a rates-owned `RatesPolicyDiagnostics` component and adjacent `ratesPolicyDiagnostics.css`.
- Timsun benchmark note: `https://timsun.net/` treats Fed funds and policy corridor pressure as part of the macro decision surface. This task intentionally ships only source-backed Federal Reserve/NY Fed/FRED policy-rate diagnostics and leaves FedWatch, statement/minutes/speech text, and meeting-probability history as source gaps.

Green tests and checks:

- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_fed_funds_module_read_adds_policy_diagnostics_from_history -q` -> pass.
- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py -q` -> `88 passed`.
- `uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py` -> pass.
- `cd web && npm run test -- tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts tests/component/features/macro/MacroRatesWorkbench.test.tsx --run` -> 2 files passed, 23 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run lint` -> ESLint passed and architecture tests 13 files passed, 73 tests passed.
- `cd web && npm run format:check` -> pass after formatting `web/src/features/macro/model/macroRatesWorkbenchModel.ts`, `web/tests/fixtures/macroFixture.ts`, and `web/tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts`.
- `uv run pytest tests/architecture/test_macro_no_compatibility_contract.py -q` -> 13 passed.

Live data probe:

- `uv run parallax config` confirmed `config_path=/Users/qinghuan/.parallax/config.yaml`, `workers_config_path=/Users/qinghuan/.parallax/workers.yaml`, macrodata enabled, and FRED API key configured by env boolean; no secret values were copied into this verification.
- A direct repository/view-builder probe against the same current PostgreSQL data path used by `/api/macro/modules/{module_id}` returned snapshot `ready`, as-of `2026-06-16`, projection lag `0`, regime `走廊稳定`, and summary `政策走廊稳定：EFFR 位于目标区间内，SOFR 相对政策锚未显示明显压力。`.
- Live rows: `目标区间` lower `3.5%`, upper `3.75%`, width `25bp`; `EFFR 位置` current `3.62%`, distance to upper `-13bp`, 1w `0bp`; `EFFR-IORB` current `-3bp`, 1w `0bp`; `SOFR-EFFR` current `3bp`, 1w `+2bp`; `SOFR 30D-EFFR` current `-2.7bp`, 1w `+0.3bp`; `DFF-EFFR` current `0bp`, 1w `0bp`.
- The live diagnostics implication was `走廊稳定：政策利率传导未给风险资产额外压力，继续观察流动性和信用确认。`; invalidation was `若 EFFR 越过目标区间或 SOFR-EFFR 单周走阔超过 5bp，重新评估政策走廊。`.
- The live `policy_diagnostics` JSON contained no raw `fed:` or `liquidity:` keys in user-facing diagnostics.

Browser smoke:

- Temporary current-code API: `127.0.0.1:8787`; temporary Vite dev server: `127.0.0.1:5175` with `VITE_DEV_API_PROXY_TARGET=http://127.0.0.1:8787`.
- Desktop Playwright probe using system Chrome on `http://127.0.0.1:5175/macro/rates/fed-funds` confirmed `政策走廊诊断 · 走廊稳定`, `目标区间`, `EFFR 位置`, `EFFR-IORB`, `SOFR-EFFR`, `SOFR 30D-EFFR`, and `DFF-EFFR` render from live data. The page had 0 console errors and 0 4xx/5xx responses during the checked requests.
- Mobile Playwright probe at `390x844` confirmed the same diagnostics title and rows stack without raw `fed:` or `liquidity:` keys; the page had 0 console errors and 0 4xx/5xx responses during the checked requests.
- The Vite process logged early proxy connection-refused messages before the API finished startup and the existing React Router future-flag warning. The temporary API process logged existing GMGN direct-WS duplicate raw-frame reconnect noise during smoke, matching prior macro tasks and unrelated to the policy diagnostics change.
- Temporary services were stopped; `lsof -nP -iTCP:8787 -sTCP:LISTEN` and `lsof -nP -iTCP:5175 -sTCP:LISTEN` returned no listeners.

## Task 31 Verification — Official Fed Text Event Bundle

Red tests:

- `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest tests/provider/test_official_fed_text_provider.py tests/unit/test_catalog.py tests/unit/test_bundles.py tests/cli/test_bundle_commands.py -q` initially failed because `official_fed_text` and `fed-text-core` did not exist.
- `uv run pytest tests/unit/domains/macro_intel/test_macrodata_bundle_importer.py::test_import_macrodata_bundle_accepts_fed_text_events_with_stable_document_series_keys tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_module_view_adds_official_event_catalysts_to_decision_console -q` initially failed because Parallax did not map Fed text series to event concepts or render their document titles as overview catalysts.

Implementation notes:

- macrodata-cli now has provider `official_fed_text` and bundle `fed-text-core` for official Federal Reserve FOMC statement, FOMC minutes, monetary-policy press-release, and speech documents.
- The provider uses only Federal Reserve official URLs: the FOMC calendar page, monetary-policy RSS, and speeches RSS. It rejects legacy aliases such as `fed_page_latest` instead of keeping compatibility names.
- Parallax maps those series to `event:fed_fomc_statement`, `event:fed_fomc_minutes`, `event:fed_monetary_policy_press_release`, and `event:fed_speech`.
- Same-day Fed documents are persisted with stable URL-derived series-key suffixes, while the raw payload preserves the original macrodata series key, official title, URL, and source timestamp.
- Overview `event_catalysts` now render Fed text documents as source-backed catalyst rows with source `Federal Reserve` and kind `fed_text`. Deleted `fed/statements` and `fed/speeches` routes remain deleted.

Green tests and checks:

- `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run ruff check src tests` -> pass.
- `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run --isolated --with mypy==1.13.0 mypy src tests` -> pass. Plain local-venv `mypy` was blocked by macOS policy on a compiled extension, so the isolated mypy run is the recorded type gate.
- `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest -q` -> `139 passed`.
- `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run macrodata source smoke --provider official_fed_text --format pretty` -> ok; sample series `fomc_statement_latest`, sample source timestamp `2026-04-29`.
- `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run macrodata bundle fetch fed-text-core --asof 2026-06-16 --format pretty` -> ready/ok, 4 of 4 series available, source chain `official_fed_text`.
- `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run macrodata bundle history fed-text-core --start 2026-05-08 --end 2026-05-08 --format pretty` -> partial with multiple same-day Fed speech documents preserved; Waller same-timestamp collisions were assigned deterministic observation timestamps while exact Federal Reserve timestamps remained in provenance.
- `uv run pytest tests/unit/domains/macro_intel/test_macrodata_bundle_importer.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py tests/unit/domains/macro_intel/test_macro_sync_service.py tests/unit/test_worker_settings.py tests/unit/test_cli_macro_commands.py tests/architecture/test_macro_no_compatibility_contract.py -q` -> `212 passed`.
- `uv run ruff check src/parallax/domains/macro_intel/_constants.py src/parallax/domains/macro_intel/services/macrodata_bundle_importer.py src/parallax/domains/macro_intel/services/macro_module_views.py src/parallax/platform/config/settings.py tests/unit/domains/macro_intel/test_macrodata_bundle_importer.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py tests/unit/domains/macro_intel/test_macro_sync_service.py tests/unit/test_worker_settings.py tests/unit/test_cli_macro_commands.py` -> pass.

Live runtime caveat resolved by Task 32:

- Immediately after Task 31, `uv run parallax macro status` in the Parallax worktree reported source-code expected `required_bundle_count=4`, `missing_required_bundle_count=1`, and missing `fed-text-core`. That was the intended stale-package diagnostic because `pyproject.toml` / `uv.lock` still pinned macrodata-cli to a Git rev that predated Task 31. Task 32 repinned Parallax to macrodata-cli `0.1.11` commit `ba8cf292afb77bfd554e0a0ebf1f3d0b0fc040fc`; the current runtime no longer depends on a host-local checkout fallback.

## Task 32 Verification — Repin Fed Text Runtime And Text Event Projection

Red/live findings:

- `uv run parallax macro sync --bundle fed-text-core --start 2026-04-01 --end 2026-06-16` first completed with `status=partial`, imported only 8 non-speech observations, and recorded `missing_series_json=["official_fed_text:speech_latest"]` with `provider_timeout` after 10 seconds. Direct macrodata history showed 23 observations, including 15 speeches, so the source bundle existed but the official speeches RSS request needed a longer provider timeout.
- Existing `macro_observation_series_rows.value_numeric` was `NOT NULL`, and request-path series refresh filtered out rows with `value_numeric IS NULL`. Official Fed text facts are document events, not numeric observations, so they could not enter the overview catalyst read model even when facts existed.

Implementation notes:

- macrodata-cli `0.1.11` commit `ba8cf292afb77bfd554e0a0ebf1f3d0b0fc040fc` adds per-request HTTP timeout support and uses a 30-second timeout for official Fed text pages/RSS. This is a source reliability fix, not a Parallax compatibility fallback.
- Parallax now pins macrodata-cli to that commit in `pyproject.toml` and `uv.lock`.
- Migration `20260616_0180_macro_event_text_series_nullable.py` drops the `NOT NULL` constraint on `macro_observation_series_rows.value_numeric`. The repository refresh query now allows non-numeric event concepts while preserving the numeric filter for ordinary macro series.

Green tests and checks:

- `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest tests/provider/test_official_fed_text_provider.py tests/unit/test_http_client.py tests/unit/test_runtime.py -q` -> `19 passed`.
- `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run ruff check src/macrodata/gateway/http_client.py src/macrodata/providers/official_fed_text.py tests/provider/test_official_fed_text_provider.py tests/unit/test_http_client.py tests/unit/test_runtime.py` -> pass.
- `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest -q` -> `141 passed`.
- `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run ruff check src tests` -> pass.
- `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run --isolated --with mypy==1.13.0 mypy src tests` -> pass.
- `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run macrodata bundle history fed-text-core --start 2026-04-01 --end 2026-06-16 --format pretty` -> `data_quality=ok`, requested 4, available 4, 23 observations, including 15 speeches through `2026-06-06`.
- `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run macrodata bundle fetch fed-text-core --asof 2026-06-16 --format pretty` -> `data_quality=ok`, requested 4, available 4.
- `uv run pytest tests/unit/domains/macro_intel/test_macro_projection_partition_refresh.py tests/unit/test_postgres_schema.py::test_macro_event_text_series_nullable_migration_allows_text_event_rows -q` -> `5 passed`.
- `uv run ruff check src/parallax/domains/macro_intel/repositories/macro_intel_repository.py src/parallax/platform/db/alembic/versions/20260616_0180_macro_event_text_series_nullable.py tests/unit/domains/macro_intel/test_macro_projection_partition_refresh.py tests/unit/test_postgres_schema.py` -> pass.

Live runtime verification:

- `uv lock` in Parallax updated macrodata-cli from `0.1.10 (a0e36192)` to `0.1.11 (ba8cf292)`.
- `uv run macrodata bundle fetch fed-text-core --asof 2026-06-16 --format pretty` in the Parallax worktree built macrodata-cli from commit `ba8cf292...` and returned `data_quality=ok`, requested 4, available 4.
- `uv run parallax macro status` reported macrodata-cli `0.1.11`, `required_bundle_count=4`, `missing_required_bundle_count=0`, `required_bundles_available=true`, 81,539 observations, 153 concepts, latest snapshot `ready`, and projection lag `0`.
- `uv run parallax db migrate` applied `20260612_0179 -> 20260616_0180`.
- `uv run parallax macro sync --bundle fed-text-core --start 2026-04-01 --end 2026-06-16` returned `status=ok`, `imported_observation_count=15`, and `max_observed_at=2026-06-06`. The latest `macro_import_runs` row has `observations_count=23`, `seen_observation_count=23`, `inserted_observation_count=15`, `noop_observation_count=8`, empty `missing_series_json`, and empty `series_errors_json`.
- Live DB facts now include `event:fed_speech` with 15 rows and `max_observed_at=2026-06-06`, plus FOMC statement/minutes and monetary-policy press releases.
- Current-code overview module payload reports `event_catalyst_count=6` and `fed_text_count=4`, including `official_fed_text:speech_latest` with description `2026-06-06 · Barr, Deregulating in a Financial Boom: What Could Go Wrong?`.

## Task 33 Verification — Inspectable Event Catalysts

Red tests:

- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_module_view_adds_official_event_catalysts_to_decision_console tests/unit/test_api_macro_contract.py::test_macro_overview_module_api_loads_event_concepts_for_decision_console -q` initially failed because overview event catalysts dropped `source_url`, Fed `document_type`, and speech `speaker` metadata from raw provenance.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run` initially failed because the macro workbench model only kept `detail/key/label/meta`, and the decision console rendered no primary-source link.

Implementation notes:

- Backend event catalyst shaping now preserves official `source_url` from provenance when present. Fed text rows additionally expose `document_type`, and speech rows derive `speaker` from explicit provenance or the official title prefix.
- Frontend macro workbench models event catalysts as typed event items with `sourceUrl`, `documentType`, and `speaker`; the decision console renders `原文` links with `target="_blank"` and keeps provider/document/speaker metadata in the item meta line.
- This is an inspectability improvement for the retained overview decision console. Deleted `fed/statements`, `fed/speeches`, and other weak macro routes remain deleted; no text-score, hawk/dove, or route-compatibility contract was added.
- `docs/CONTRACTS.md` and `src/parallax/domains/macro_intel/ARCHITECTURE.md` now state that event catalysts can carry primary-source URLs and Fed document metadata while remaining outside numeric macro-core scoring.

Green tests and checks:

- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_module_view_adds_official_event_catalysts_to_decision_console tests/unit/test_api_macro_contract.py::test_macro_overview_module_api_loads_event_concepts_for_decision_console -q` -> `2 passed`.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run` -> 2 files passed, 21 tests passed.
- `uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py` -> pass.
- `cd web && npm run typecheck` first failed because the event catalyst filter still narrowed to the old `MacroDecisionConsoleItem`; after fixing the predicate to `MacroDecisionConsoleEventItem`, the command passed.
- `cd web && npm run lint` -> ESLint passed and architecture tests 13 files passed, 73 tests passed.
- `cd web && npm run test:architecture` -> 13 files passed, 73 tests passed.
- `cd web && npm run format:check` first reported formatting drift in `tests/component/features/macro/MacroModulePages.test.tsx`; after Prettier on that file, `format:check` passed.
- `uv run python scripts/validate_sdd_artifacts.py` -> pass after a pre-existing active SDD background-citation token issue in `2026-06-12-kappa-cqrs-governance-root-fix/spec.md` was corrected by removing machine-checked backticks around cited Macro table names.
- `uv run python scripts/regen_sdd_work_index.py && uv run python scripts/regen_sdd_work_index.py --check` -> pass.

Browser/layout evidence:

- `cd web && npm run test:e2e -- tests/e2e/golden-paths/macro-responsive-audit.spec.ts --project=desktop-1366` -> 1 Playwright test passed. The spec audits all macro product routes, including `/macro`, across mobile 390/430, tablet 834, compact 1096, desktop 1366, and desktop 1920 viewport sizes for overflow, label fragmentation, hidden-route leakage, unhandled API requests, and console/page errors.

## Task 34 Verification — BLS Official Calendar Catalysts

Red tests:

- `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest tests/provider/test_official_calendar_provider.py tests/unit/test_catalog.py::test_catalog_contains_official_calendar_event_series tests/unit/test_bundles.py::test_macro_calendar_core_is_separate_from_numeric_regime_bundle tests/cli/test_bundle_commands.py::test_macro_calendar_core_bundle_fetch_uses_official_sources -q` initially failed with unknown `bls_cpi_next`, missing catalog entries, `macro-calendar-core` size 3 instead of 6, and bundle coverage requested/available 3 instead of 6.
- `uv run pytest tests/unit/domains/macro_intel/test_macro_migration_contract.py::test_macro_constants_map_bls_calendar_event_concepts -q` initially failed because `official_calendar:bls_cpi_next` had no Parallax event mapping.

Implementation notes:

- macrodata-cli `official_calendar` now parses official BLS CPI, Employment Situation, and PPI schedule pages, preserving release date, release time, source URL, and reference period.
- `macro-calendar-core` now requests six official calendar series: FOMC, BEA GDP, BEA PCE, BLS CPI, BLS Employment Situation, and BLS PPI. These remain outside `macro-core`.
- Parallax maps the three BLS calendar observations to `event:bls_cpi_next`, `event:bls_employment_next`, and `event:bls_ppi_next` with display metadata. No deleted calendar/surprise route, compatibility alias, or actual-vs-consensus field was added.
- Packaging boundary: Task 36 resolves the runtime gap by publishing macrodata-cli
  `0.1.12` at Git rev `25ba5281d04a0ddc81ab6a07c4a5784b698100f9` and
  repinning Parallax to that portable dependency instead of a host-local checkout.

Green tests and checks:

- `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest tests/provider/test_official_calendar_provider.py tests/unit/test_catalog.py::test_catalog_contains_official_calendar_event_series tests/unit/test_bundles.py::test_macro_calendar_core_is_separate_from_numeric_regime_bundle tests/cli/test_bundle_commands.py::test_macro_calendar_core_bundle_fetch_uses_official_sources tests/cli/test_bundle_commands.py::test_event_bundle_history_commands_are_first_class_sync_surfaces -q` -> 9 passed.
- `uv run pytest tests/unit/domains/macro_intel/test_macro_migration_contract.py::test_macro_constants_map_bls_calendar_event_concepts -q` -> 1 passed.
- `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest tests/provider/test_official_calendar_provider.py tests/unit/test_catalog.py tests/unit/test_bundles.py tests/cli/test_bundle_commands.py -q` -> 56 passed.
- `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run ruff check src tests` -> pass.
- `uv run pytest tests/unit/domains/macro_intel/test_macro_migration_contract.py -q` -> 16 passed.
- `uv run ruff check src/parallax/domains/macro_intel/_constants.py tests/unit/domains/macro_intel/test_macro_migration_contract.py` -> pass.
- `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run macrodata bundle fetch macro-calendar-core --asof 2026-06-16 --format pretty` -> `ok=true`, `data_quality=ok`, coverage requested 6 / available 6. BLS rows returned Employment Situation `2026-07-02`, CPI `2026-07-14`, and PPI `2026-07-15`, each at `08:30 AM` with `reference_period="June 2026"`.
- `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run macrodata bundle history macro-calendar-core --start 2026-06-16 --end 2026-07-31 --format pretty` -> `ok=true`, `data_quality=ok`, coverage requested 6 / available 6, including the three BLS event observations plus Fed/BEA events.

## Task 35 Verification — Stale Event Bundle Series Diagnostics

Red tests:

- `uv run pytest tests/unit/test_cli_macro_commands.py::test_macrodata_runtime_state_reports_missing_event_bundle_series tests/unit/test_cli_macro_commands.py::test_macro_status_requires_importable_event_bundle_series -q` initially failed because `macrodata_runtime_state` did not accept `required_bundle_series`, and `parallax macro status` only passed numeric `MACRO_PROVIDER_SERIES_TO_CONCEPT` plus bundle names.

Implementation notes:

- `macrodata_runtime_state` now accepts a per-bundle required-series mapping and reports `missing_required_bundle_series_by_bundle` plus a prefixed sample such as `macro-calendar-core:official_calendar:bls_cpi_next`.
- `parallax macro status` now checks `MACRO_IMPORTABLE_PROVIDER_SERIES_TO_CONCEPT` in the installed macrodata catalog, while checking per-bundle membership separately so event series are not incorrectly required inside numeric `macro-core`.
- This does not repin or use the local macrodata-cli checkout; it makes stale packaged macrodata dependencies visible before operators debug missing catalysts.

Green tests and checks:

- `uv run pytest tests/unit/test_cli_macro_commands.py::test_macrodata_runtime_state_reports_missing_event_bundle_series tests/unit/test_cli_macro_commands.py::test_macro_status_requires_importable_event_bundle_series -q` -> 2 passed.
- `uv run pytest tests/unit/test_cli_macro_commands.py -q` -> 37 passed.
- `uv run ruff check src/parallax/integrations/macrodata/runner.py src/parallax/app/surfaces/cli/commands/macro.py tests/unit/test_cli_macro_commands.py` -> pass.

## Task 36 Verification — BLS Runtime Repin And Live Catalyst Projection

Red tests:

- `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest tests/unit/test_runtime.py::test_package_version_advances_for_bls_calendar_release -q` initially failed while the package still reported `0.1.11`.
- `uv run pytest tests/architecture/test_project_structure.py::test_macrodata_cli_is_packaged_from_versioned_git_source -q` initially failed because Parallax still pinned macrodata-cli Git rev `ba8cf292afb77bfd554e0a0ebf1f3d0b0fc040fc`.
- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_event_catalysts_show_bls_release_time_and_reference_period -q` initially failed because BLS catalyst descriptions used only date and days-until, dropping provenance `event_time_et` and `reference_period`.

Implementation notes:

- macrodata-cli was bumped to `0.1.12`, committed on branch `codex/macrodata-bls-calendar`, and pushed at Git rev `25ba5281d04a0ddc81ab6a07c4a5784b698100f9`.
- Parallax `pyproject.toml` and `uv.lock` now pin macrodata-cli to that Git rev, keeping runtime sync portable and avoiding any host-local `/Users/.../macrodata-cli` dependency.
- Overview calendar catalyst descriptions now read both `event_time` and source-provided `event_time_et`, plus `reference_period` when present. BLS CPI, Employment Situation, and PPI therefore show `08:30 AM` and `June 2026` in the first-screen decision console.
- `docs/CONTRACTS.md` and `src/parallax/domains/macro_intel/ARCHITECTURE.md` now state that official calendar catalysts preserve release timing and reference periods when available.

Green tests and checks:

- `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest tests/unit/test_runtime.py tests/provider/test_official_calendar_provider.py tests/unit/test_catalog.py tests/unit/test_bundles.py tests/cli/test_bundle_commands.py -q` -> 62 passed.
- `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run ruff check src tests` -> pass.
- `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run macrodata bundle fetch macro-calendar-core --asof 2026-06-16 --format json` -> `ok=true`, coverage requested 6 / available 6, including BLS CPI, Employment Situation, and PPI.
- `uv lock --upgrade-package macrodata-cli` updated macrodata-cli from `0.1.11 (ba8cf292)` to `0.1.12 (25ba5281)`.
- `uv run pytest tests/architecture/test_project_structure.py::test_macrodata_cli_is_packaged_from_versioned_git_source -q` -> 1 passed.
- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_event_catalysts_show_bls_release_time_and_reference_period tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_module_view_adds_official_event_catalysts_to_decision_console -q` -> 2 passed.
- `uv run parallax macro status` reported macrodata-cli `0.1.12`, required series count 157, missing required series 0, required bundle count 4, missing required bundles 0, missing required bundle series 0, and `required_bundle_series_available=true`.
- `uv run macrodata bundle fetch macro-calendar-core --asof 2026-06-16 --format json` inside the Parallax worktree installed macrodata-cli from GitHub rev `25ba5281...` and returned coverage requested 6 / available 6.

Live runtime verification:

- `uv run parallax config` confirmed runtime config at `/Users/qinghuan/.parallax/config.yaml` and workers config at `/Users/qinghuan/.parallax/workers.yaml`; macrodata was enabled and FRED was configured by redacted boolean. No secret values were copied into this verification.
- `uv run parallax db health` reported migration `20260616_0180`, expected migration `20260616_0180`, and `migration_status=ready`.
- `uv run parallax macro sync --bundle macro-calendar-core --start 2026-06-16 --end 2026-07-31` returned `status=ok`, `imported_observation_count=3`, `max_seen_observed_at=2026-07-30`, and changed/inserted BLS observations spanning `2026-07-02` to `2026-07-15`.
- Direct repository verification found 3 BLS facts in `macro_observations` and 3 current rows in `macro_observation_series_rows` for `event:bls_employment_next`, `event:bls_cpi_next`, and `event:bls_ppi_next`; every projected row has a non-empty payload hash and there are no remaining BLS `macro_projection_dirty_targets`.
- The latest sync audit row for `macro-calendar-core` shows 9 observations seen, 3 inserted, 6 no-op, `status=ok`, and `max_observed_at=2026-07-30`.
- Current-code overview module view renders BLS catalysts as:
  - `CPI 发布`: `2026-07-14 · 还有 28 天 · 08:30 AM · June 2026`
  - `就业报告发布`: `2026-07-02 · 还有 16 天 · 08:30 AM · June 2026`
  - `PPI 发布`: `2026-07-15 · 还有 29 天 · 08:30 AM · June 2026`
    Each row carries its official BLS `source_url`.

## Task 37 Verification — MOVE Rates-Volatility Proxy

Red tests:

- `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest tests/unit/test_bundles.py::test_bundle_constants_include_economy_volatility_and_credit_series tests/unit/test_catalog.py::test_catalog_documents_public_macro_terminal_proxies tests/unit/test_runtime.py::test_package_version_advances_for_move_proxy_release -q` initially failed because `volatility-core` lacked `yahoo:^MOVE`, the catalog did not know the series, and package version was still `0.1.12`.
- `uv run pytest tests/unit/domains/macro_intel/test_macro_migration_contract.py::test_macro_constants_map_move_rates_volatility_proxy tests/unit/domains/macro_intel/test_macro_module_catalog.py::test_volatility_vix_page_includes_move_rates_volatility_proxy tests/unit/domains/macro_intel/test_macro_module_views.py::test_volatility_vix_module_read_adds_volatility_diagnostics_from_history -q` initially failed because Parallax lacked the `yahoo:^MOVE -> vol:move` mapping, module catalog inclusion, and diagnostics row.
- `uv run pytest tests/architecture/test_project_structure.py::test_macrodata_cli_is_packaged_from_versioned_git_source -q` initially failed because Parallax still pinned macrodata-cli Git rev `25ba5281d04a0ddc81ab6a07c4a5784b698100f9`.
- After the first live projection, `uv run pytest tests/unit/domains/macro_intel/test_macro_migration_contract.py::test_macro_constants_map_move_rates_volatility_proxy -q` intentionally failed again until `vol:move` was kept in `MACRO_CORE_CONCEPTS` but excluded from the global 126-point history gate.

Implementation notes:

- macrodata-cli now exposes `yahoo:^MOVE` as `ICE BofA MOVE Index` in the catalog and includes it in `volatility-core` / `macro-core`; package version is `0.1.13`.
- macrodata-cli was committed and pushed on `codex/macrodata-bls-calendar` at Git rev `1fde95d5b4ddff9bdec60cc9e1d25ec9027b10ce`.
- Parallax `pyproject.toml` and `uv.lock` now pin that macrodata-cli rev, keeping the runtime portable and avoiding host-local checkout fallback.
- Parallax maps `yahoo:^MOVE` to `vol:move`, adds metadata, includes it in `volatility/vix` optional/chart/table evidence, and emits a backend `MOVE 美债波动率` diagnostics row when persisted history is available.
- `vol:move` remains a core visible concept but is not a global 126-point history blocker, so short bootstrap history does not downgrade the macro snapshot from ready to partial. Licensed ICE/Bloomberg MOVE or intraday redistribution remains a source backlog item.

Green tests and checks:

- `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest tests/unit/test_bundles.py tests/unit/test_catalog.py tests/unit/test_runtime.py -q` -> 46 passed.
- `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run ruff check src tests` -> pass.
- `uv lock --upgrade-package macrodata-cli` updated macrodata-cli from `0.1.12 (25ba5281)` to `0.1.13 (1fde95d5)`.
- `uv run pytest tests/architecture/test_project_structure.py::test_macrodata_cli_is_packaged_from_versioned_git_source tests/unit/domains/macro_intel/test_macro_migration_contract.py::test_macro_constants_map_move_rates_volatility_proxy tests/unit/domains/macro_intel/test_macro_module_catalog.py::test_volatility_vix_page_includes_move_rates_volatility_proxy tests/unit/domains/macro_intel/test_macro_module_views.py::test_volatility_vix_module_read_adds_volatility_diagnostics_from_history -q` -> 4 passed.
- `uv run macrodata bundle fetch volatility-core --asof 2026-06-16 --format json` inside Parallax returned `yahoo:^MOVE` observed `2026-06-12` at about `69.36`; Yahoo source health was `ok`. FRED public CSV timed out in that one probe, which did not affect the MOVE row.

Live runtime verification:

- `uv run parallax config` confirmed runtime config at `/Users/qinghuan/.parallax/config.yaml`, workers config at `/Users/qinghuan/.parallax/workers.yaml`, macrodata enabled, and FRED configured by redacted boolean. No secret values were printed.
- `uv run parallax db health` reported migration `20260616_0180`, expected migration `20260616_0180`, and `migration_status=ready`.
- `uv run parallax macro sync --bundle volatility-core --start 2026-05-16 --end 2026-06-16` returned `retryable_error` because macrodata-cli has range history commands for `macro-core` and event bundles, not `volatility-core`; this is an operator-command boundary, not a MOVE provider failure.
- `uv run parallax macro sync --bundle macro-core --start 2026-06-01 --end 2026-06-16` returned `status=partial`, `imported_observation_count=129`, and `max_observed_at=2026-06-16`; partial came from existing transient FRED/Treasury provider errors while Yahoo rows, including `^MOVE`, imported.
- Direct DB verification found 10 `macro_observations` and 10 projected `macro_observation_series_rows` for `vol:move`, newest `2026-06-12`, every projected row carrying a payload hash.
- A one-shot current-code macro view projection loaded 139 macro-core targets and rebuilt the snapshot as `status=ready`, `history_coverage_ratio=1.0`, with 5 existing data gaps unrelated to MOVE.
- `uv run parallax macro status` now reports macrodata-cli `0.1.13`, required series count 158, missing required series 0, concept count 158, required history concept count 137, history-ready true, `latest_snapshot.status=ready`, `feature_count=139`, and projection lag 0.
- Current-code `build_macro_module_view("volatility/vix", ...)` against the live PostgreSQL path returns a MOVE diagnostics row: `MOVE 美债波动率`, current `69.4`, 1w `-5.8`, 1m unavailable from the short imported window, status `正常`.

## Task 38 Verification — Treasury Auction Calendar Catalysts

Red tests:

- `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest tests/provider/test_treasury_auction_provider.py tests/unit/test_bundles.py tests/unit/test_catalog.py tests/unit/test_runtime.py tests/cli/test_bundle_commands.py::test_treasury_auction_core_bundle_fetch_uses_official_fiscaldata tests/cli/test_bundle_commands.py::test_event_bundle_history_commands_are_first_class_sync_surfaces -q` initially failed because `TreasuryAuctionProvider` did not accept `today`, `treasury-auction-core` still requested 9 series, the catalog lacked `*_next_auction_days`, and package version was still `0.1.13`.
- `uv run pytest tests/architecture/test_project_structure.py::test_macrodata_cli_is_packaged_from_versioned_git_source tests/unit/domains/macro_intel/test_macro_migration_contract.py::test_macro_constants_map_treasury_auction_calendar_event_concepts tests/unit/domains/macro_intel/test_macrodata_bundle_importer.py::test_import_macrodata_bundle_accepts_event_bundles_without_expanding_numeric_macro_core tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_module_view_adds_official_event_catalysts_to_decision_console -q` initially failed because Parallax still pinned macrodata-cli `1fde95d5...`, did not map `treasury_auction:*_next_auction_days`, and treated upcoming auction rows as generic auction results.
- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_event_catalysts_prioritize_near_upcoming_treasury_auction_calendar -q` initially failed because overview catalysts were truncated in repository/source order and could hide nearer Treasury auction calendar rows behind less urgent events.

Implementation notes:

- macrodata-cli now parses official Treasury tentative schedule XML with `defusedxml`, emits `treasury_auction:2y_next_auction_days`, `treasury_auction:10y_next_auction_days`, and `treasury_auction:30y_next_auction_days`, and keeps TIPS/FRN rows out of the nominal 2Y/10Y/30Y auction calendar lane.
- `treasury-auction-core` now has 12 series: 3 upcoming calendar rows plus the existing 9 completed result metrics. Calendar rows preserve announcement date, auction date, settlement date, reopening, TIPS, floating-rate, security term/type, and official source URL in provenance.
- macrodata-cli was bumped to `0.1.14`, committed on branch `codex/macrodata-bls-calendar`, and pushed at Git rev `a90da8c3f4c7139924043d9d496493ded4326d50`.
- Parallax `pyproject.toml` and `uv.lock` now pin macrodata-cli to that Git rev, keeping runtime sync portable and avoiding host-local checkout fallback.
- Parallax maps the three new series to `event:treasury_auction_2y_next`, `event:treasury_auction_10y_next`, and `event:treasury_auction_30y_next`, keeps them out of numeric `MACRO_CORE_CONCEPTS`, and renders them in overview as `auction_calendar` catalysts.
- Overview event catalysts are now sorted by nearest upcoming calendar risk before de-duplication and truncation, so a nearer 2Y auction row wins over a later 2Y row and Treasury supply events are not hidden by DB concept ordering.

Green tests and checks:

- `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest -q` -> 144 passed.
- `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run ruff check src tests` -> pass.
- `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run macrodata bundle fetch treasury-auction-core --asof 2026-06-16 --format json` -> `ok=true`, coverage requested 12 / available 12; upcoming events included 2Y `2026-06-23`, 10Y `2026-07-08`, and 30Y `2026-07-09`.
- `uv lock` updated macrodata-cli from `0.1.13 (1fde95d5)` to `0.1.14 (a90da8c3)` and added transitive `defusedxml v0.7.1`.
- `uv run pytest tests/architecture/test_project_structure.py tests/unit/domains/macro_intel/test_macro_migration_contract.py tests/unit/domains/macro_intel/test_macrodata_bundle_importer.py tests/unit/domains/macro_intel/test_macro_module_views.py -q` -> 110 passed.
- `uv run ruff check src/parallax/domains/macro_intel/_constants.py src/parallax/domains/macro_intel/services/macro_module_views.py tests/architecture/test_project_structure.py tests/unit/domains/macro_intel/test_macro_migration_contract.py tests/unit/domains/macro_intel/test_macrodata_bundle_importer.py tests/unit/domains/macro_intel/test_macro_module_views.py` -> pass.

Live runtime verification:

- `uv run parallax config` confirmed runtime config at `/Users/qinghuan/.parallax/config.yaml`, workers config at `/Users/qinghuan/.parallax/workers.yaml`, macrodata enabled, and FRED configured by redacted boolean. No secret values were printed.
- `uv run parallax macro status` reports macrodata-cli `0.1.14`, required series count 161, missing required series 0, required bundle count 4, missing required bundle series 0, concept count 161, history-ready true, `latest_snapshot.status=ready`, and projection lag 0.
- `uv run parallax macro sync --bundle treasury-auction-core --start 2026-06-16 --end 2026-07-31` returned `ok=true`, `status=partial`, `imported_observation_count=4`, and `max_observed_at=2026-07-27`; partial is expected for this window because completed May auction result metrics are outside the requested range.
- Direct DB verification found projected rows for `event:treasury_auction_2y_next`, `event:treasury_auction_10y_next`, and `event:treasury_auction_30y_next`. Rows included 2Y auctions on `2026-06-23` and `2026-07-27`, 10Y on `2026-07-08`, and 30Y on `2026-07-09`, each from source `treasury_auction` with official tentative schedule provenance.
- Current-code overview module view now renders nearest upcoming Treasury supply catalysts in the decision console. The live catalyst list includes:
  - `2Y 国债拍卖日历`: `2026-06-23 · 还有 7 天 · 2026-06-18 公告 · 2026-06-30 交割`
  - `10Y 国债拍卖日历`: `2026-07-08 · 还有 22 天 · 2026-07-02 公告 · 2026-07-15 交割 · Reopen`
    Both rows carry `source_url=https://home.treasury.gov/system/files/221/Tentative-Auction-Schedule.xml` and no deleted `rates/auctions` route was restored.

## Task 39 Verification — Frontend Unsupported Macro Route Shell Removal

Red tests:

- `cd web && npm run test -- tests/unit/features/macro/model/macroRoutes.test.ts tests/routes/macro.route.test.tsx --run` initially failed because `parseMacroRouteTail("fed")` still returned `routeKind: "unsupported"` and `/macro/not-real` still rendered the macro-specific unsupported route panel instead of an ordinary route error.

Implementation notes:

- Frontend macro route types no longer include `MacroPageKind = "unsupported"` or `MacroProductTier = "unsupported"`.
- `parseMacroRouteTail` now returns `null` for unknown/deleted macro tails and no longer emits `wasUnknown` metadata.
- `web/src/routes/macro.route.tsx` turns unknown/deleted macro tails into the ordinary route-error surface with `404 Not Found`.
- `MacroWorkbenchRoute` no longer has an unsupported prop branch, and `macroShell.css` no longer includes `.macro-route-unsupported` dead styling.
- The e2e deleted-route guard now asserts every hard-deleted macro URL renders `404 Not Found` with no macro module navigation and no `不支持的宏观页面` panel.

Green tests and checks:

```text
$ cd web && npm run test -- tests/unit/features/macro/model/macroRoutes.test.ts tests/unit/features/macro/model/macroPageRegistry.test.ts tests/routes/macro.route.test.tsx --run && npm run typecheck && npm run lint && npm run test:e2e -- tests/e2e/golden-paths/macro-terminal.spec.ts --project=desktop-1366 -g "hard-deleted routes"
Test files passed: 3 Vitest route/model files; 13 architecture files; 1 Playwright desktop route-error check.
Tests passed: 16 Vitest route/model tests; 73 architecture tests; 1 Playwright test.
exit code: 0
```

- `cd web && npm run test -- tests/unit/features/macro/model/macroRoutes.test.ts tests/unit/features/macro/model/macroPageRegistry.test.ts tests/routes/macro.route.test.tsx --run` -> 3 files passed, 16 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture tests 13 files passed, 73 tests passed.
- `cd web && npm run test:e2e -- tests/e2e/golden-paths/macro-terminal.spec.ts --project=desktop-1366 -g "hard-deleted routes"` -> 1 passed.

## 2026-06-17 Continuation — Trade Map Workbench Structuring

Red tests:

- `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx -t "renders overview page grammar" --run` initially failed because the Trade Map panel rendered the backend historical review, paper portfolio, trust, holding-period review, and action checklist as one flat list with no accessible subheadings. The expected failure was `Unable to find an accessible element with the role "heading" and name "五资产雷达"`.

Implementation notes:

- `MacroDecisionConsolePanel` now renders Trade Map details through a small local `TradeDetailBlock` helper with explicit headings for `当前表达`, `五资产雷达`, `组合复盘`, `历史可信度`, `持有期复盘`, and `行动清单`.
- `macroWorkbench.css` keeps the styling under the macro workbench namespace, stays below the 500-line side-effect CSS budget, and does not restyle shared UI primitives.
- The frontend still consumes only backend strings from `decision_console.trade_map`; it does not compute returns, P&L, trust, or holding-period outcomes in React.

Green tests and checks:

- `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx -t "renders overview page grammar" --run` -> 1 passed.
- `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx tests/unit/features/macro/model/macroWorkbenchModel.test.ts --run` -> 2 files passed, 21 tests passed.
- `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroRatesWorkbench.test.tsx --run` -> 3 files passed, 32 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run test:architecture` -> 13 files passed, 73 tests passed.
- `cd web && npm run lint` -> ESLint passed; architecture tests 13 files passed, 73 tests passed.
- `cd web && npm run format:check` -> pass after applying Prettier to the two files it reported: `web/src/features/macro/model/macroRoutes.ts` and `web/tests/component/features/macro/MacroRatesWorkbench.test.tsx`.
- `cd web && npm run test:e2e -- tests/e2e/golden-paths/macro-responsive-audit.spec.ts --project=desktop-1366` -> 1 Playwright golden-path test passed.

Live read-model and browser notes:

- `uv run parallax config` confirmed operator-owned runtime config at `/Users/qinghuan/.parallax/config.yaml` and workers config at `/Users/qinghuan/.parallax/workers.yaml`; macrodata is enabled and FRED is configured by redacted boolean.
- `uv run parallax macro status` reports macrodata-cli `0.1.14`, required bundle count `4`, missing required bundle series `0`, observations `81,571`, concepts `161`, latest snapshot `ready`, facts max observed date `2026-06-16`, and projection lag `0`.
- A read-only live query over `macro_observation_series_rows` found enough 60-day projected rows for every Trade Map asset: `asset:ndx` 40, `crypto:btc` 60, `asset:gld` 40, `asset:spx` 41, and `asset:tlt` 41.
- Current worktree code plus the live DB builds overview `decision_console.trade_map[0]` with `historical_review`, `portfolio_review`, and `holding_period_review`; sample count is 5. The already-running API on `127.0.0.1:8765` had not been restarted with this backend code, so the in-app browser against that old process showed only the current-expression legs. The Playwright golden path above uses current-code mocked API fixtures for layout coverage.

## 2026-06-17 Continuation — Macro Category Alias Hard Delete

Red test:

- `cd web && npm run test -- tests/unit/features/macro/model/macroRoutes.test.ts --run` initially failed because `parseMacroRouteTail("rates")` still returned `routeKind: "redirect"` with canonical path `/macro/rates/fed-funds` instead of using the ordinary deleted-route behavior.

Implementation notes:

- `MacroRouteResolution` no longer has a `redirect` variant.
- `MACRO_PARENT_ROUTE_REDIRECTS` was deleted from `macroRoutes.ts`, and `macro.route.tsx` no longer imports or renders React Router `Navigate` for macro category aliases.
- `/macro/rates`, `/macro/liquidity`, `/macro/economy`, `/macro/volatility`, and `/macro/credit` now resolve like unknown macro tails: ordinary route-error surface, no macro module nav, and no API request for an overview fallback.
- The responsive Playwright audit now asserts those five paths are hard-deleted. Its console collector only ignores the expected `404 Not Found` render/page errors while the current page URL is one of the hard-deleted category routes; all other console/page errors still fail the test.

Green tests and checks:

- `cd web && npm run test -- tests/unit/features/macro/model/macroRoutes.test.ts --run` -> 1 file passed, 4 tests passed.
- `cd web && npm run test -- tests/routes/macro.route.test.tsx --run` -> 1 file passed, 14 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run format:check` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture tests 13 files passed, 73 tests passed.
- `cd web && npm run test:e2e -- tests/e2e/golden-paths/macro-responsive-audit.spec.ts --project=desktop-1366` -> 1 Playwright golden-path test passed after the expected-404 console filter was scoped to hard-deleted category URLs.

## 2026-06-17 Continuation — Two-Week Scenario Cases

Red tests:

- `uv run pytest tests/unit/domains/macro_intel/test_macro_scenario_engine.py -q` initially failed with `KeyError: 'scenario_cases'` because `build_macro_scenario(...)` did not emit timsun-style base/upside/downside trade cases.
- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_module_view_surfaces_global_scenario_and_data_health -q` initially failed because overview `decision_console` did not pass through `scenario_json.scenario_cases`.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts --run` initially failed because `buildMacroDecisionConsole(...)` did not expose `scenarioCases`.
- `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx -t "renders overview page grammar" --run` initially failed because the decision panel had no `未来 2 周情景` region.

Implementation notes:

- `build_macro_scenario(...)` now emits a current `scenario_cases` field for all non-data-gap regimes. The field contains `基准情景`, `乐观情景`, and `悲观情景` with probability, two-week thesis, trade expression, entry condition, stop, and invalidation.
- Overview `decision_console` passes through `scenario_cases` from the persisted snapshot; the API does not recompute this block as a compatibility fallback when old snapshots lack it.
- Frontend workbench model maps backend `scenario_cases` into display-only rows. The React panel renders a `未来 2 周情景` section and does not compute probability, thesis, trade, stop, or invalidation locally.
- The live operator DB was refreshed through the formal `macro_projection_dirty_targets` + `MacroViewProjectionWorker.run_once_sync()` path after the code change. The worker claimed one current target, wrote one current snapshot row, and produced a `ready` `funding_stress` snapshot. A read-only current-code overview view then reported three scenario cases: `基准情景`, `乐观情景`, and `悲观情景` with probabilities `50%`, `25%`, and `25%`.

Green tests and checks:

- `uv run pytest tests/unit/domains/macro_intel/test_macro_scenario_engine.py -q` -> 4 passed.
- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_module_view_surfaces_global_scenario_and_data_health -q` -> 1 passed.
- `uv run pytest tests/unit/domains/macro_intel/test_macro_scenario_engine.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py -q` -> 97 passed.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts --run` -> 1 file passed, 10 tests passed.
- `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx -t "renders overview page grammar" --run` -> 1 targeted test passed.
- `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx tests/unit/features/macro/model/macroWorkbenchModel.test.ts --run` -> 2 files passed, 22 tests passed.
- `cd web && npm run format:check` -> pass after applying Prettier to `web/src/features/macro/model/macroWorkbenchModel.ts` and `web/tests/component/features/macro/MacroModulePages.test.tsx`.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture tests 13 files passed, 73 tests passed.
- `cd web && npm run test:e2e -- tests/e2e/golden-paths/macro-responsive-audit.spec.ts --project=desktop-1366` -> 1 Playwright golden-path test passed.

## 2026-06-17 Continuation — Yield Curve Spread History And Tenor Split

Red tests:

- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_yield_curve_module_read_adds_curve_diagnostics_from_history -q` first errored in the test fixture because the local helper lacked labels for `rates:real_5y`, `rates:real_10y`, and `inflation:5y_breakeven`. After fixing the fixture labels, the same test failed as intended with `KeyError: 'spread_history'` because backend `curve_diagnostics` did not yet emit bounded spread-history data or tenor decomposition.
- `cd web && npm run test -- tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts --run` failed with `TypeError: Cannot read properties of undefined (reading '0')` because the rates workbench model did not expose `spreadHistories`.
- `cd web && npm run test -- tests/component/features/macro/MacroRatesWorkbench.test.tsx -t "renders yield curve diagnostics as a decision block" --run` failed with `Unable to find an element with the text: 历史利差` because the curve diagnostics panel still rendered only the current spread rows.

Implementation notes:

- `rates/yield-curve` backend `curve_diagnostics` now includes bounded `spread_history` series for 2s10s, 3m10y, and 5s30s, derived from existing persisted FRED Treasury histories. It also includes `tenor_comparison` rows for 5Y and 10Y using existing nominal Treasury, TIPS real-yield, and breakeven histories. No deleted rates route, FedWatch proxy, provider call, or compatibility field was added.
- The rates workbench model formats backend `spread_history` and `tenor_comparison` into display-only rows. React renders a `历史利差` visual block and a `期限拆分` block inside the existing curve diagnostics panel; it does not calculate curve shape, changes, drivers, or macro scoring locally.
- A read-only live check against the operator runtime built the current `rates/yield-curve` module view through `build_macro_module_view(...)`. The live snapshot was `ready`, `shape_label` was `牛陡`, `spread_history_count` was 3 with labels `2s10s`, `3m10y`, `5s30s`, the first spread series had 64 bounded points, and `tenor_count` was 2 with labels `5Y` and `10Y`.

Green tests and checks:

- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_yield_curve_module_read_adds_curve_diagnostics_from_history -q` -> 1 passed.
- `cd web && npm run test -- tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts --run` -> 1 file passed, 6 tests passed.
- `cd web && npm run test -- tests/component/features/macro/MacroRatesWorkbench.test.tsx -t "renders yield curve diagnostics as a decision block" --run` -> 1 targeted test passed.
- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py -q` -> 93 passed.
- `cd web && npm run test -- tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts tests/component/features/macro/MacroRatesWorkbench.test.tsx --run` -> 2 files passed, 17 tests passed.
- `uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py` -> pass.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run format:check` initially reported `web/src/features/macro/model/macroRatesWorkbenchModel.ts` and `web/src/features/macro/ui/rates/RatesCurveDiagnostics.tsx`; after `npx prettier --write` on those two files, `cd web && npm run format:check` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture tests 13 files passed, 73 tests passed.
- `cd web && npm run test:e2e -- tests/e2e/golden-paths/macro-responsive-audit.spec.ts --project=desktop-1366` -> 1 Playwright golden-path test passed across the macro route/viewport matrix, including `/macro/rates/yield-curve`.

## 2026-06-17 Continuation — Real Rates Diagnostics

Red tests:

- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_real_rates_module_read_adds_real_rate_diagnostics_from_history -q` failed with `KeyError: 'real_rate_diagnostics'` because `rates/real-rates` still had only generic module-read text and tables.
- `cd web && npm run test -- tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts -t "formats real rate diagnostics" --run` failed because `view.realRateDiagnostics` was undefined.
- `cd web && npm run test -- tests/component/features/macro/MacroRatesWorkbench.test.tsx -t "renders real rate diagnostics" --run` failed because there was no accessible `实际利率诊断` region on `/macro/rates/real-rates`.

Implementation notes:

- `rates/real-rates` now emits backend `real_rate_diagnostics` when persisted FRED TIPS and breakeven histories support it. The payload includes 5Y/10Y/30Y real-yield rows, 5Y/10Y breakeven plus 5Y5Y forward rows, current and 1w/1m/3m changes, regime language, implication, and invalidation.
- The rates workbench model formats the backend rows for display. `RatesRealRateDiagnostics` renders the decision block after the primary chart with adjacent owner CSS. React does not compute real-rate changes, regime, implication, or invalidation locally.
- No deleted route, FedWatch/OIS proxy, source backlog label, provider call, or compatibility field was added.
- A read-only live check against the operator runtime built the current `rates/real-rates` module view through `build_macro_module_view(...)`. The live snapshot was `ready`, regime label was `实际利率压力`, real-yield row count was 3 with labels `5Y Real`, `10Y Real`, `30Y Real`, and inflation row count was 3 with labels `5Y Breakeven`, `10Y Breakeven`, and `5Y5Y Forward`.

Green tests so far:

- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_real_rates_module_read_adds_real_rate_diagnostics_from_history -q` -> 1 passed.
- `cd web && npm run test -- tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts -t "formats real rate diagnostics" --run` -> 1 targeted test passed.
- `cd web && npm run test -- tests/component/features/macro/MacroRatesWorkbench.test.tsx -t "renders real rate diagnostics" --run` -> 1 targeted test passed.
- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_real_rates_module_read_adds_real_rate_diagnostics_from_history tests/unit/domains/macro_intel/test_macro_module_views.py::test_yield_curve_module_read_adds_curve_diagnostics_from_history -q` -> 2 passed.
- `cd web && npm run test -- tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts tests/component/features/macro/MacroRatesWorkbench.test.tsx --run` -> 2 files passed, 19 tests passed.
- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py -q` -> 94 passed.
- `uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py` -> pass after wrapping two long assertion lines.
- `cd web && npm run format:check` initially reported `web/tests/component/features/macro/MacroRatesWorkbench.test.tsx` and `web/tests/fixtures/macroFixture.ts`; after `npx prettier --write` on those two files, `cd web && npm run format:check` -> pass.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture tests 13 files passed, 73 tests passed.
- `cd web && npm run test:e2e -- tests/e2e/golden-paths/macro-responsive-audit.spec.ts --project=desktop-1366` -> 1 Playwright golden-path test passed across the macro route/viewport matrix, including `/macro/rates/real-rates`.

## 2026-06-17 Continuation — Event Heatmap

Red tests:

- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_decision_console_adds_event_heatmap -q` initially failed with `KeyError: 'event_heatmap'` because overview `decision_console` still exposed only the broader catalyst list.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run` then failed as expected because `buildMacroDecisionConsole(...)` did not expose `eventHeatmap`, and the overview decision panel had no event-heatmap section.
- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_event_heatmap_uses_untruncated_calendar_candidates -q` then failed because `event_heatmap` was derived from the already truncated six-row `event_catalysts` display list and dropped the seventh and eighth near-event candidates.

Implementation notes:

- Overview `decision_console.event_heatmap` now comes from future 0-14 day `calendar`/`auction_calendar` catalysts and recent official Fed text catalysts. It classifies each row by event window, severity, category, impact, watch text, and source URL.
- Completed Treasury auction result rows remain in `event_catalysts`; Fed text rows are still inspectable catalysts and now also appear in the event heatmap as policy communication rows.
- `MacroDecisionConsolePanel` renders a dedicated `事件热力` section between `未来 2 周情景` and `事件催化`. The frontend model formats backend fields only; React does not compute event severity, event categories, or macro impact.
- No deleted route was restored: `rates/auctions`, Fed text pages, and calendar/surprise pages remain ordinary deleted surfaces. Auction tail remains unimplemented until a reliable when-issued-yield source exists.
- Backend event candidate generation is now split from display truncation: `event_catalysts` still renders the first six sorted catalysts, while `event_heatmap` can use the full deduplicated candidate list and return up to eight near 0-14 day calendar rows.

Green tests and checks:

- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_decision_console_adds_event_heatmap -q` -> 1 passed.
- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_decision_console_adds_event_heatmap tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_event_heatmap_uses_untruncated_calendar_candidates -q` -> 2 passed.
- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py -q` -> 96 passed.
- `uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py` -> pass.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run` -> 2 files passed, 23 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run format:check` initially reported `web/tests/component/features/macro/MacroModulePages.test.tsx` and `web/tests/fixtures/macroFixture.ts`; after `npx prettier --write` on those two files, `cd web && npm run format:check` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture tests 13 files passed, 73 tests passed.
- `cd web && npm run test:e2e -- tests/e2e/golden-paths/macro-responsive-audit.spec.ts --project=desktop-1366` -> 1 Playwright golden-path test passed across the macro route/viewport matrix.
- Read-only live overview probe through `build_macro_module_view("overview", ...)` with operator config produced `snapshot_status=ready`, `event_heatmap_count=4`, labels `FOMC 决议`, `2Y 国债拍卖日历`, `BEA GDP 发布`, `PCE 发布`, and windows `0-3d`, `4-7d`, `8-14d`, `8-14d`.
- `uv run python scripts/regen_sdd_work_index.py`, `uv run python scripts/validate_sdd_artifacts.py`, `uv run python scripts/regen_sdd_work_index.py --check`, and `git diff --check` -> pass.

## 2026-06-17 Continuation — GDPNow Nowcast Row

Red tests:

- `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest tests/unit/test_catalog.py::test_catalog_contains_gdpnow_nowcast_series tests/unit/test_bundles.py::test_bundle_constants_include_economy_volatility_and_credit_series -q` initially failed because `fred:GDPNOW` was not in the catalog and `economy-core` still expected 21 series.
- `uv run pytest tests/architecture/test_project_structure.py::test_macrodata_cli_is_packaged_from_versioned_git_source tests/unit/domains/macro_intel/test_macro_migration_contract.py::test_macro_constants_map_gdpnow_nowcast_concept tests/unit/domains/macro_intel/test_macro_module_catalog.py::test_gdp_and_employment_pages_include_remaining_growth_and_labor_evidence tests/unit/domains/macro_intel/test_macro_module_views.py::test_gdp_module_read_adds_growth_diagnostics_from_history -q` initially failed because Parallax had no `economy:gdp_nowcast` mapping, no GDP module optional/table row, and no growth diagnostics row.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run` initially failed because the macro workbench model and fixture did not format a `current_pct` GDPNow row.

Implementation notes:

- External macrodata-cli now exposes `fred:GDPNOW` as `GDPNow`, adds it to `economy-core`, bumps package version to `0.1.15`, and was committed/pushed as `a01ed678ad578cd6406f93b20558da4ccd1fc660` on `codex/macrodata-bls-calendar`.
- Parallax is repinned to that packaged Git rev, maps `fred:GDPNOW` to `economy:gdp_nowcast`, marks the concept optional history, and adds GDPNow metadata plus an optional GDP table row.
- `economy/gdp` backend `growth_diagnostics` now includes a source-backed `gdpnow_saar` row with current `% SAAR`, optional 1m change when history exists, and deterministic nowcast status labels. React only formats backend fields and does not compute nowcast math.
- No economy calendar/surprise page, consensus field, prior field, revision field, fake surprise row, host-local macrodata fallback, or compatibility route was added.

Green tests and checks:

- `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest tests/unit/test_catalog.py::test_catalog_contains_gdpnow_nowcast_series tests/unit/test_bundles.py::test_bundle_constants_include_economy_volatility_and_credit_series -q` -> 2 passed.
- `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest tests/unit/test_catalog.py tests/unit/test_bundles.py tests/unit/test_runtime.py -q` -> 47 passed.
- `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run ruff check src tests` -> pass.
- `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest -q` -> 145 passed.
- `uv run pytest tests/architecture/test_project_structure.py::test_macrodata_cli_is_packaged_from_versioned_git_source tests/unit/domains/macro_intel/test_macro_migration_contract.py::test_macro_constants_map_gdpnow_nowcast_concept tests/unit/domains/macro_intel/test_macro_module_catalog.py::test_gdp_and_employment_pages_include_remaining_growth_and_labor_evidence tests/unit/domains/macro_intel/test_macro_module_views.py::test_gdp_module_read_adds_growth_diagnostics_from_history -q` -> 4 passed.
- `uv run ruff check src/parallax/domains/macro_intel/_constants.py src/parallax/domains/macro_intel/services/macro_module_catalog.py src/parallax/domains/macro_intel/services/macro_module_views.py tests/architecture/test_project_structure.py tests/unit/domains/macro_intel/test_macro_migration_contract.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/domains/macro_intel/test_macro_module_views.py` -> pass.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run` -> 2 files passed, 23 tests passed.

Live runtime verification:

- `uv run macrodata catalog show fred:GDPNOW --format json` from the Parallax worktree returned macrodata-cli `0.1.15`, provider `fred`, unit `percent_saar`, and source URL `https://fred.stlouisfed.org/series/GDPNOW`.
- `uv run parallax macro status` reports macrodata-cli `0.1.15`, required series count `162`, missing required series count `0`, missing required bundle series count `0`, history-ready `true`, and latest snapshot `ready`.
- `uv run parallax macro sync --bundle macro-core --start 2026-06-16 --end 2026-06-16` returned `ok=true`, `status=partial`, `imported_observation_count=2`, and `max_observed_at=2026-06-16`; partial is expected for a one-day macro-core sync because many macro-core series do not publish every calendar day.
- The formal `MacroViewProjectionWorker.run_once_sync()` path was used after enqueueing one current dirty target when the queue was empty. It processed 1 target, wrote 1 snapshot row, kept snapshot status `ready`, and source scanned 77,888 rows.
- Live DB/read-model probe confirmed `concept_count=162`, one `economy:gdp_nowcast` observation from `fred:GDPNOW` with latest value `2.8314` on `2026-04-01`, `features_json` contains `economy:gdp_nowcast`, and the current `economy/gdp` module view emits a GDPNow row: `current_pct=2.83`, `change_1m_pct=null`, `status=nowcast_resilient`, `status_label=Nowcast 韧性`.

## 2026-06-17 Continuation — NY Fed Repo-Depth Funding Slice

Red tests:

- `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest tests/provider/test_nyfed_provider.py::test_nyfed_secured_reference_rates_parse_repo_depth_series tests/provider/test_nyfed_provider.py::test_nyfed_secured_reference_rate_volumes_parse_as_millions -q` initially failed because `BGCR`, `TGCR`, and `*_VOLUME` datasets were unknown.
- `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest tests/unit/test_catalog.py::test_catalog_contains_nyfed_repo_depth_series tests/unit/test_bundles.py::test_bundle_constants_include_rates_and_liquidity_series tests/unit/test_runtime.py -q` initially failed because the catalog, bundle constants, and package version did not include the new NY Fed repo-depth series.
- `uv run pytest tests/architecture/test_project_structure.py::test_macrodata_cli_is_packaged_from_versioned_git_source tests/unit/domains/macro_intel/test_macro_migration_contract.py::test_macro_constants_map_nyfed_repo_depth_concepts tests/unit/domains/macro_intel/test_macro_module_catalog.py::test_rrp_tga_page_absorbs_public_market_operations_evidence tests/unit/domains/macro_intel/test_macro_module_views.py::test_liquidity_rrp_tga_module_read_adds_liquidity_diagnostics_from_history -q` initially failed because Parallax had no mapping, module table/catalog rows, or repo-depth diagnostics.
- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_liquidity_rrp_tga_module_uses_module_observations_for_repo_depth_optional_series -q` initially failed with `模块覆盖 0/12`, proving projected module observations were not supplementing snapshot-only features.

Implementation notes:

- External macrodata-cli now exposes NY Fed `BGCR`, `TGCR`, `SOFR_VOLUME`, `BGCR_VOLUME`, and `TGCR_VOLUME`, parses reference-rate `type=rate` and `type=volume` responses, converts `volumeInBillions` to `millions_usd`, adds the five series to `LIQUIDITY_CORE` / `MACRO_CORE`, bumps package version to `0.1.16`, and was committed/pushed as `06b94b1ccf5840ed34205498c4fddd43f796bb9d` on `codex/macrodata-bls-calendar`.
- Parallax is repinned to that packaged Git rev, maps the five NY Fed series to `liquidity:bgcr`, `liquidity:tgcr`, `liquidity:sofr_volume`, `liquidity:bgcr_volume`, and `liquidity:tgcr_volume`, and folds them into retained `liquidity/rrp-tga` optional/table/chart evidence instead of restoring `liquidity/subsurface`.
- `liquidity/rrp-tga` backend diagnostics now include `SOFR-TGCR 深度压力` and `SOFR 成交量` rows. Single-point repo-depth facts can render as rows/tiles while their long history bootstraps; the diagnostic block still requires at least one liquidity row with history-backed change.
- `build_macro_module_view(...)` now supplements non-overview module feature maps with projected module observations when snapshot `features_json` lacks optional module concepts. This keeps regime snapshot ownership intact while preventing fresh module facts from being falsely shown as missing.

Green tests and checks:

- `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest -q` -> 151 passed.
- `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run ruff check src tests` -> pass.
- `uv run pytest tests/architecture/test_project_structure.py::test_macrodata_cli_is_packaged_from_versioned_git_source tests/unit/domains/macro_intel/test_macro_migration_contract.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py -q` -> 149 passed.
- `uv run ruff check src/parallax/domains/macro_intel/_constants.py src/parallax/domains/macro_intel/services/macro_module_catalog.py src/parallax/domains/macro_intel/services/macro_module_views.py tests/architecture/test_project_structure.py tests/unit/domains/macro_intel/test_macro_migration_contract.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py` -> pass.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run` -> 2 files passed, 23 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run format:check` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture tests 13 files passed, 73 tests passed.
- `cd web && npm run test:e2e -- tests/e2e/golden-paths/macro-responsive-audit.spec.ts --project=desktop-1366` -> 1 Playwright golden-path test passed. A prior attempt with obsolete project name `chromium-desktop` failed because current projects are `desktop-1366`, `desktop-1920`, `tablet-834`, `mobile-390`, and `mobile-430`.

Live runtime verification:

- `uv run macrodata catalog show nyfed:SOFR_VOLUME --format json` from the Parallax worktree returned `SOFR Underlying Volume`, provider `nyfed`, dataset `SOFR_VOLUME`, unit `millions_usd`, and source URL `https://markets.newyorkfed.org/api/rates/secured/sofr/search.json`.
- `uv run python -c "import importlib.metadata as m; print(m.version('macrodata-cli'))"` returned `0.1.16`.
- `uv run parallax macro status` reported macrodata-cli `0.1.16`, required series count `167`, missing required series count `0`, missing required bundle series count `0`, concept count `167` after sync, and five new repo-depth concepts with one point each on `2026-06-15`.
- Direct NY Fed API checks showed `2026-06-16` reference-rate rows were empty while `2026-06-15` returned SOFR `3.69`, TGCR `3.67`, and SOFR underlying volume `3147` billions. `uv run parallax macro sync --bundle macro-core --start 2026-06-15 --end 2026-06-15` then returned `ok=true`, `status=partial`, `imported_observation_count=13`, and `max_observed_at=2026-06-15`.
- The formal projection path had already consumed the dirty targets by the time `MacroViewProjectionWorker.run_once_sync()` was called manually; it reported `claimed=0`. `uv run parallax macro status` nevertheless showed `publication_state.row_count=5252` and the five new concepts projected into `macro_observation_series_rows`.
- Direct current-code `liquidity/rrp-tga` module probe through `build_macro_module_view(...)` reported `confidence_label=模块覆盖 13/13`, no missing-concept contradictions, tiles/table rows for `liquidity:fed_assets`, `liquidity:reserve_balances`, `liquidity:bgcr`, `liquidity:tgcr`, `liquidity:sofr_volume`, `liquidity:bgcr_volume`, and `liquidity:tgcr_volume`, plus diagnostics rows `SOFR-TGCR 深度压力 current_bp=2.0` and `SOFR 成交量 current_bn=3147.0`.

## 2026-06-17 Continuation — NY Fed Unsecured Funding Corridor Slice

Red tests:

- `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest tests/provider/test_nyfed_provider.py::test_nyfed_reference_rates_parse_funding_depth_series tests/provider/test_nyfed_provider.py::test_nyfed_reference_rate_volumes_parse_as_millions tests/unit/test_catalog.py::test_catalog_contains_nyfed_unsecured_funding_series tests/unit/test_bundles.py::test_bundle_constants_include_rates_and_liquidity_series tests/unit/test_runtime.py -q` initially failed because NY Fed `EFFR`, `OBFR`, `EFFR_VOLUME`, and `OBFR_VOLUME` were unknown datasets/catalog entries, `rates-market-core` still had 28 series, and the package version was still `0.1.16`.
- `uv run pytest tests/unit/domains/macro_intel/test_macro_migration_contract.py::test_macro_constants_map_nyfed_unsecured_funding_concepts tests/unit/domains/macro_intel/test_macro_module_catalog.py::test_fed_funds_page_absorbs_nyfed_unsecured_funding_depth tests/unit/domains/macro_intel/test_macro_module_views.py::test_fed_funds_module_read_adds_policy_diagnostics_from_history -q` initially failed because Parallax had no NY Fed unsecured mapping, no retained `rates/fed-funds` optional/table rows, and no OBFR/volume policy-diagnostics rows.
- `cd web && npm run test -- --run tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts` and `cd web && npm run test -- --run tests/component/features/macro/MacroRatesWorkbench.test.tsx` first caught that policy-diagnostics volume rows formatted negative billions as `$-43B`; this was fixed to `-$43B`.

Implementation notes:

- External macrodata-cli now exposes NY Fed unsecured reference-rate `EFFR` and `OBFR` plus `EFFR_VOLUME` and `OBFR_VOLUME`, parses `type=rate` and `type=volume` responses, converts `volumeInBillions` to `millions_usd`, adds the four series to `RATES_MARKET_CORE` / `MACRO_CORE`, bumps package version to `0.1.17`, and was committed/pushed as `ac06e171833a99e19761dc69a2e6a222d7f80754` on `codex/macrodata-bls-calendar`.
- Parallax is repinned to that packaged Git rev. NY Fed `EFFR` maps to the existing `fed:effr` concept with higher source priority than the FRED mirror; `OBFR`, `EFFR_VOLUME`, and `OBFR_VOLUME` map to `fed:obfr`, `fed:effr_volume`, and `fed:obfr_volume`.
- `rates/fed-funds` now absorbs the unsecured funding depth in the retained module: OBFR enters the policy chart/table, EFFR/OBFR volumes enter the table and backend `policy_diagnostics`, and short-history NY Fed funding-depth concepts are optional for global history readiness while remaining visible in module data health.
- The frontend rates workbench formats backend `current_bn` policy rows as signed dollar billions. React still does not compute policy spreads, funding-volume status, or macro regime.
- Deleted pages remain deleted: no `rates/expectations`, Fed text page, auction page, or `liquidity/subsurface` route was restored.

Green tests and checks:

- `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest tests/provider/test_nyfed_provider.py::test_nyfed_reference_rates_parse_funding_depth_series tests/provider/test_nyfed_provider.py::test_nyfed_reference_rate_volumes_parse_as_millions tests/unit/test_catalog.py::test_catalog_contains_nyfed_unsecured_funding_series tests/unit/test_bundles.py::test_bundle_constants_include_rates_and_liquidity_series tests/unit/test_runtime.py -q` -> 17 passed.
- `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest -q` -> 156 passed.
- `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run ruff check src tests` -> pass.
- `uv run pytest tests/unit/domains/macro_intel/test_macro_migration_contract.py::test_macro_constants_map_nyfed_unsecured_funding_concepts tests/unit/domains/macro_intel/test_macro_module_catalog.py::test_fed_funds_page_absorbs_nyfed_unsecured_funding_depth tests/unit/domains/macro_intel/test_macro_module_views.py::test_fed_funds_module_read_adds_policy_diagnostics_from_history -q` -> 3 passed.
- `uv run pytest tests/unit/domains/macro_intel/test_macro_migration_contract.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/domains/macro_intel/test_macrodata_bundle_importer.py tests/unit/domains/macro_intel/test_macro_sync_service.py -q` -> 156 passed.
- `uv run pytest tests/architecture/test_project_structure.py::test_macrodata_cli_is_packaged_from_versioned_git_source -q` -> 1 passed.
- `cd web && npm run test -- --run tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts` -> 1 file passed, 7 tests passed.
- `cd web && npm run test -- --run tests/component/features/macro/MacroRatesWorkbench.test.tsx` -> 1 file passed, 12 tests passed.

Live runtime verification:

- `uv run macrodata catalog show nyfed:OBFR_VOLUME --format json` from the Parallax worktree returned `OBFR Underlying Volume`, provider `nyfed`, dataset `OBFR_VOLUME`, unit `millions_usd`, and source URL `https://markets.newyorkfed.org/api/rates/unsecured/obfr/search.json`.
- `uv run parallax macro status` reported macrodata-cli `0.1.17`, required series count `171`, missing required series count `0`, missing required bundle series count `0`, `history_ready=true`, latest snapshot `ready`, and concept count `170` after sync because `nyfed:EFFR` intentionally folds into existing `fed:effr`.
- `uv run parallax macro sync --bundle macro-core --start 2026-06-15 --end 2026-06-16` returned `ok=true`, `status=partial`, `imported_observation_count=6`, and `max_observed_at=2026-06-16`; partial is expected for a narrow macro-core window because many macro-core series do not publish every calendar day.
- Direct current-code `rates/fed-funds` module probe through `build_macro_module_view(...)` reported `snapshot_status=ready`, `confidence_label=模块覆盖 11/11`, policy rows `obfr_effr_spread`, `effr_volume`, and `obfr_volume`, and table rows `fed:obfr`, `fed:effr_volume`, and `fed:obfr_volume`. Live row values included `OBFR-EFFR current_bp=0.0`, `EFFR 成交量 current_bn=102.0`, and `OBFR 成交量 current_bn=196.0`.

## 2026-06-17 Continuation — Official Cboe VVIX/SKEW Tail-Risk Depth

Red tests:

- `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest tests/provider/test_cboe_provider.py::test_cboe_index_provider_fetches_vvix_and_skew_history tests/unit/test_catalog.py::test_catalog_contains_cboe_vvix_and_skew_series tests/unit/test_bundles.py::test_volatility_core_includes_cboe_tail_risk_series tests/unit/test_runtime.py::test_runtime_registers_cboe_provider -q` initially failed because there was no Cboe provider, no `cboe:VVIX` / `cboe:SKEW` catalog entries, no volatility-core membership, and no runtime provider registration.
- `uv run pytest tests/unit/domains/macro_intel/test_macro_migration_contract.py::test_macro_constants_map_cboe_vvix_and_skew_tail_risk_indexes tests/unit/domains/macro_intel/test_macro_module_catalog.py::test_volatility_vix_page_absorbs_cboe_tail_risk_depth tests/unit/domains/macro_intel/test_macro_module_views.py::test_volatility_vix_module_read_adds_volatility_diagnostics_from_history -q` initially failed because Parallax had no Cboe mapping, no retained volatility module rows, and no VVIX/SKEW diagnostics.

Implementation notes:

- External macrodata-cli now exposes an official Cboe CSV provider for `cboe:VVIX` and `cboe:SKEW`, using `https://cdn.cboe.com/api/global/us_indices/daily_prices/VVIX_History.csv` and `https://cdn.cboe.com/api/global/us_indices/daily_prices/SKEW_History.csv`. It parses daily `DATE,VVIX` and `DATE,SKEW` rows, adds both series to volatility-core / macro-core runtime coverage, bumps package version to `0.1.18`, and was committed/pushed as `e02eef03feae897ddc9664f6d2bfead0ced8b2d9` on `codex/macrodata-bls-calendar`.
- Parallax is repinned to that packaged Git rev. `cboe:VVIX` maps to `vol:vvix`, `cboe:SKEW` maps to `vol:skew`, and both are required-history numeric concepts so missing history remains visible rather than hidden.
- Retained `volatility/vix` now absorbs VVIX and SKEW into tiles, table rows, availability notes, and backend `volatility_diagnostics` rows. Source labels render as `Cboe`.
- Deleted pages remain deleted: no `volatility/dashboard`, hidden volatility page, compatibility route, fake VIX futures curve, or static tail-risk placeholder was added.

Green tests and checks:

- `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest -q` -> 162 passed.
- `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run ruff check src tests` -> pass.
- `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run macrodata catalog show cboe:VVIX --format json` -> provider `cboe`, source URL `https://cdn.cboe.com/api/global/us_indices/daily_prices/VVIX_History.csv`.
- `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run macrodata fetch series cboe:SKEW --start 2026-06-10 --end 2026-06-16 --format json` -> live rows through `2026-06-15`, including `144.32` on `2026-06-15`.
- `uv run pytest tests/unit/domains/macro_intel/test_macro_migration_contract.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/architecture/test_project_structure.py::test_macrodata_cli_is_packaged_from_versioned_git_source -q` -> 116 passed.
- `uv run ruff check src/parallax/domains/macro_intel/_constants.py src/parallax/domains/macro_intel/services/macro_module_catalog.py src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_migration_contract.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/architecture/test_project_structure.py` -> pass.
- `cd web && npm test -- --run tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx` -> 2 files passed, 23 tests passed.

Live runtime verification:

- `uv run python -c "import importlib.metadata as m; print(m.version('macrodata-cli'))"` returned `0.1.18`.
- `uv run macrodata fetch series cboe:VVIX --start 2026-06-10 --end 2026-06-16 --format json` returned VVIX rows through `2026-06-15`: `108.16`, `100.63`, `93.82`, and `87.58`.
- `uv run macrodata fetch series cboe:SKEW --start 2026-06-10 --end 2026-06-16 --format json` returned SKEW rows through `2026-06-15`: `143.08`, `142.98`, `142.60`, and `144.32`.
- `uv run parallax macro sync --bundle macro-core --start 2025-12-01 --end 2026-06-16` returned `ok=true`, `status=partial`, `imported_observation_count=2160`, `max_observed_at=2026-06-16`, and `asof_date=2026-06-16`; partial is expected because not every macro-core series publishes on every day in the window.
- Direct DB verification found 135 `macro_observations` and 135 projected `macro_observation_series_rows` each for `vol:vvix` and `vol:skew`, with oldest `2025-12-01`, latest `2026-06-15`, source `cboe`, and series keys `cboe:VVIX` / `cboe:SKEW`.
- The formal projection path was used after enqueueing a current dirty target. Current-code `MacroViewProjectionWorker.run_once_sync(now_ms=...)` claimed 1 target, scanned 79,369 source rows, wrote 1 snapshot row, loaded 150 targets, and produced a `ready` `funding_stress` snapshot.
- `uv run parallax macro status` reported macrodata-cli `0.1.18`, required series count `173`, missing required series count `0`, missing required bundle series count `0`, observations `83,191`, concepts `172`, required history concept count `139`, `history_ready=true`, latest snapshot `ready`, feature count `150`, `facts_max_observed_at=2026-06-16`, and projection lag `0`.
- Direct current-code `volatility/vix` module probe through `build_macro_module_view(...)` reported tiles `vol:vvix` value `87.58` source `Cboe` observed `2026-06-15` and `vol:skew` value `144.32` source `Cboe` observed `2026-06-15`; `vix_term_proxy_table` source cells for both rows also render `Cboe`.

## 2026-06-17 Continuation — Official Cboe VIX9D Near-Term Premium

Red tests:

- `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest tests/provider/test_cboe_provider.py::test_cboe_provider_parses_official_index_history_csv tests/unit/test_catalog.py::test_catalog_documents_public_macro_terminal_proxies tests/unit/test_bundles.py::test_bundle_constants_include_economy_volatility_and_credit_series tests/unit/test_runtime.py::test_runtime_cboe_provider_fetches_official_volatility_index_history tests/unit/test_runtime.py::test_package_version_advances_for_cboe_volatility_release -q` initially failed because `cboe:VIX9D` was absent from the Cboe provider/catalog/volatility-core/runtime and the package version had not advanced.
- `uv run pytest tests/unit/domains/macro_intel/test_macro_migration_contract.py::test_macro_constants_map_cboe_vvix_and_skew_tail_risk_indexes tests/unit/domains/macro_intel/test_macro_module_catalog.py::test_volatility_vix_page_absorbs_cboe_tail_risk_depth tests/unit/domains/macro_intel/test_macro_module_views.py::test_volatility_vix_module_read_adds_volatility_diagnostics_from_history tests/architecture/test_project_structure.py::test_macrodata_cli_is_packaged_from_versioned_git_source -q` initially failed because Parallax had no VIX9D mapping, no retained volatility module row, no `VIX9D-VIX` diagnostics row, and still pinned the older macrodata-cli rev.
- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_volatility_vix_module_merges_module_observation_history_for_existing_features -q` initially failed because module views used a single-point snapshot feature even when persisted module observations supplied deeper history.

Implementation notes:

- External macrodata-cli now exposes official Cboe `cboe:VIX9D` from `https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX9D_History.csv`. The Cboe provider parses OHLC history CSVs using `CLOSE` when the dataset-specific value column is absent, adds VIX9D to volatility-core, bumps package version to `0.1.19`, and was committed/pushed as `719634cccf32bb5d69aa3bc6a2d52b61b874f4f9` on `codex/macrodata-bls-calendar`.
- Parallax is repinned to that packaged Git rev. `cboe:VIX9D` maps to required-history numeric concept `vol:vix9d`, retained `volatility/vix` absorbs it into tiles/chart/table, and backend diagnostics now emit `VIX9D-VIX 近端溢价` before `VIX3M-VIX`.
- `build_macro_module_view(...)` now merges deeper/newer persisted module observation history into existing snapshot features. Live VIX9D diagnostics therefore use 135 stored Cboe rows instead of a single current feature point.
- Deleted pages remain deleted: no `volatility/dashboard`, VIX futures curve placeholder, hidden route, compatibility alias, or static VIX9D row was added.

Green tests and checks:

- `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest -q` -> 163 passed.
- `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run ruff check src tests` -> pass.
- `uv run pytest tests/unit/domains/macro_intel/test_macro_migration_contract.py::test_macro_constants_map_cboe_vvix_and_skew_tail_risk_indexes tests/unit/domains/macro_intel/test_macro_module_catalog.py::test_volatility_vix_page_absorbs_cboe_tail_risk_depth tests/unit/domains/macro_intel/test_macro_module_views.py::test_volatility_vix_module_read_adds_volatility_diagnostics_from_history tests/architecture/test_project_structure.py::test_macrodata_cli_is_packaged_from_versioned_git_source -q` -> 4 passed.
- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_volatility_vix_module_merges_module_observation_history_for_existing_features tests/unit/domains/macro_intel/test_macro_module_views.py::test_volatility_vix_module_read_adds_volatility_diagnostics_from_history -q` -> 2 passed.
- `cd web && npm run test -- --run tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx` -> 2 files passed, 23 tests passed.

Live runtime verification:

- `uv run python -c "import importlib.metadata as m; print(m.version('macrodata-cli'))"` returned `0.1.19`.
- `uv run macrodata catalog show cboe:VIX9D --format json` returned provider `cboe`, name `Cboe 9-Day Volatility Index`, and source URL `https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX9D_History.csv`.
- `uv run macrodata fetch series cboe:VIX9D --start 2026-06-10 --end 2026-06-16 --format json` returned rows through `2026-06-15`: `25.67`, `20.66`, `17.26`, and `15.58`.
- `uv run parallax macro sync --bundle macro-core --start 2025-12-01 --end 2026-06-16` returned `ok=true`, `status=partial`, `imported_observation_count=665`, `max_observed_at=2026-06-16`, and `asof_date=2026-06-16`; partial is expected because not every macro-core series publishes every day in the window.
- Direct DB verification found 135 `macro_observations` and 135 projected `macro_observation_series_rows` for `vol:vix9d`, with oldest `2025-12-01`, latest `2026-06-15`, source `cboe`, and series key `cboe:VIX9D`.
- `uv run parallax macro status` reported macrodata-cli `0.1.19`, required series count `174`, missing required series count `0`, missing required bundle series count `0`, observations `83,348`, concepts `173`, required history concept count `140`, `history_ready=true`, latest snapshot `ready`, `facts_max_observed_at=2026-06-16`, and projection lag `0`.
- Direct current-code `volatility/vix` module probe through `build_macro_module_view(...)` reported VIX9D tile history points `135`, source `Cboe`, table source `Cboe`, and diagnostic row `VIX9D-VIX 近端溢价` with current `-0.6`, 1w `-1.4`, and 1m `+1.4` points.

## 2026-06-17 Continuation — Official Cboe VIX1D Same-Day Premium

Red tests:

- `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest tests/provider/test_cboe_provider.py::test_cboe_provider_parses_official_index_history_csv tests/unit/test_catalog.py::test_catalog_documents_public_macro_terminal_proxies tests/unit/test_bundles.py::test_bundle_constants_include_economy_volatility_and_credit_series tests/unit/test_runtime.py::test_runtime_cboe_provider_fetches_official_volatility_index_history tests/unit/test_runtime.py::test_package_version_advances_for_cboe_volatility_release -q` initially failed because `cboe:VIX1D` was absent from the Cboe provider/catalog/volatility-core/runtime and the package version had not advanced.
- `uv run pytest tests/unit/domains/macro_intel/test_macro_migration_contract.py::test_macro_constants_map_cboe_vvix_and_skew_tail_risk_indexes tests/unit/domains/macro_intel/test_macro_module_catalog.py::test_volatility_vix_page_absorbs_cboe_tail_risk_depth tests/unit/domains/macro_intel/test_macro_module_views.py::test_volatility_vix_module_read_adds_volatility_diagnostics_from_history tests/architecture/test_project_structure.py::test_macrodata_cli_is_packaged_from_versioned_git_source -q` initially failed because Parallax had no VIX1D mapping, no retained volatility module row, no `VIX1D-VIX` diagnostics row, and still pinned the older macrodata-cli rev.
- `uv run pytest tests/unit/test_api_macro_contract.py::test_macro_module_api_returns_backend_module_view tests/unit/domains/macro_intel/test_macro_module_views.py::test_volatility_vix_module_read_adds_volatility_diagnostics_from_history -q` guarded the leaf-module history-read fix after live probing showed a newly added series could otherwise render with only one current point.

Implementation notes:

- External macrodata-cli now exposes official Cboe `cboe:VIX1D` from `https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX1D_History.csv`. The existing Cboe OHLC parser reads `CLOSE`, adds VIX1D to volatility-core, bumps package version to `0.1.20`, and was committed/pushed as `739d0bab59f4ac8b905008478aeefbeb541e4a9b` on `codex/macrodata-bls-calendar`.
- Parallax is repinned to that packaged Git rev. `cboe:VIX1D` maps to required-history numeric concept `vol:vix1d`, retained `volatility/vix` absorbs it into tiles/chart/table, and backend diagnostics now emit `VIX1D-VIX 当日溢价` before `VIX9D-VIX`.
- `/api/macro/modules/{module_id}` now reads persisted concept history for retained leaf modules through `observations_for_concepts(...)` instead of `latest_observations(...)`. This keeps newly introduced source-backed module concepts decision-usable immediately after sync, with 1w/1m diagnostics rather than a single current point.
- Deleted pages remain deleted: no `volatility/dashboard`, VIX futures curve placeholder, hidden route, compatibility alias, or static VIX1D row was added.

Green tests and checks:

- `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest -q` -> 165 passed.
- `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run ruff check src tests` -> pass.
- `uv run pytest tests/unit/domains/macro_intel/test_macro_migration_contract.py::test_macro_constants_map_cboe_vvix_and_skew_tail_risk_indexes tests/unit/domains/macro_intel/test_macro_module_catalog.py::test_volatility_vix_page_absorbs_cboe_tail_risk_depth tests/unit/domains/macro_intel/test_macro_module_views.py::test_volatility_vix_module_read_adds_volatility_diagnostics_from_history tests/architecture/test_project_structure.py::test_macrodata_cli_is_packaged_from_versioned_git_source -q` -> 4 passed.
- `uv run pytest tests/unit/test_api_macro_contract.py::test_macro_module_api_returns_backend_module_view tests/unit/domains/macro_intel/test_macro_module_views.py::test_volatility_vix_module_read_adds_volatility_diagnostics_from_history -q` -> 2 passed.
- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/domains/macro_intel/test_macro_migration_contract.py tests/architecture/test_project_structure.py::test_macrodata_cli_is_packaged_from_versioned_git_source -q` -> 117 passed.
- `cd web && npm run test -- --run tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx` -> 2 files passed, 23 tests passed.
- `uv run ruff check src/parallax/app/surfaces/api/routes_macro.py src/parallax/domains/macro_intel/_constants.py src/parallax/domains/macro_intel/services/macro_module_catalog.py src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/test_api_macro_contract.py tests/unit/domains/macro_intel/test_macro_migration_contract.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/architecture/test_project_structure.py` -> pass.
- `uv lock --check` and `git diff --check` -> pass.

Live runtime verification:

- `uv run parallax config` exited 0. Redacted summary: config path `/Users/qinghuan/.parallax/config.yaml`; workers config path `/Users/qinghuan/.parallax/workers.yaml`; macrodata enabled; FRED configured through env name `FINANCE_FRED_API_KEY`; no secret values printed.
- `uv run python -c "import importlib.metadata as m; print(m.version('macrodata-cli'))"` returned `0.1.20`.
- `uv run macrodata catalog show cboe:VIX1D --format json` returned provider `cboe`, name `Cboe 1-Day Volatility Index`, and source URL `https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX1D_History.csv`.
- `uv run macrodata fetch series cboe:VIX1D --start 2026-06-10 --end 2026-06-16 --format json` returned rows through `2026-06-15`: `23.85`, `21.09`, `19.12`, and `12.92`.
- `uv run parallax macro sync --bundle macro-core --start 2025-12-01 --end 2026-06-16` returned `ok=true`, `status=partial`, `imported_observation_count=556`, `max_observed_at=2026-06-16`, and `asof_date=2026-06-16`; partial remains expected because `fred:EVZCLS` has no observations in this window.
- Direct DB verification found 135 `macro_observations` and 135 projected `macro_observation_series_rows` for `vol:vix1d`, with oldest `2025-12-01`, latest `2026-06-15`, source `cboe`, and series key `cboe:VIX1D`.
- `uv run parallax macro status` reported macrodata-cli `0.1.20`, required series count `175`, missing required series count `0`, missing required bundle series count `0`, observations `83,483`, concepts `174`, required history concept count `141`, `history_ready=true`, latest snapshot `ready`, `facts_max_observed_at=2026-06-16`, and projection lag `0`.
- Direct current-code `volatility/vix` module probe through API-equivalent module history loading reported VIX1D tile history points `135`, value `12.92`, source `Cboe`, observed `2026-06-15`, and diagnostic row `VIX1D-VIX 当日溢价` with current `-3.3`, 1w `-0.4`, and 1m `-1.6` points.

## 2026-06-17 Continuation — NFCI Financial Conditions In Credit Stress

Red tests:

- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_credit_stress_module_read_adds_credit_diagnostics_from_history tests/unit/domains/macro_intel/test_macro_module_views.py::test_credit_stress_module_read_promotes_nfci_tightening_when_spreads_lag -q` initially failed because `credit_diagnostics.rows` omitted `NFCI 金融条件` and a tightening NFCI history still produced the `contained` regime.
- `cd web && npm run test -- --run tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx` initially failed because the credit diagnostics formatter dropped index-valued rows, so the fixture's NFCI row was not rendered.

Implementation notes:

- `credit/stress` now adds an `NFCI 金融条件` row from existing `credit:nfci` history, with current, 1w, 1m, 3m index changes and optional `credit:anfci` adjusted index. This uses already-retained FRED/Chicago Fed concepts; no new route, compatibility shell, or hidden credit page was added.
- Credit regime logic now promotes `financial_conditions_tightening` when NFCI tightens before HY/IG/CCC spreads fully confirm. Higher-severity HY/CCC credit stress and tail widening still take precedence.
- The web credit diagnostics model now formats `current_index` / `change_*_index` rows so source-backed financial-condition rows are visible in the retained leaf module page.

Green tests and checks:

- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_credit_stress_module_read_adds_credit_diagnostics_from_history tests/unit/domains/macro_intel/test_macro_module_views.py::test_credit_stress_module_read_promotes_nfci_tightening_when_spreads_lag -q` -> 2 passed.
- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/domains/macro_intel/test_macro_migration_contract.py tests/unit/test_api_macro_contract.py tests/architecture/test_project_structure.py::test_macrodata_cli_is_packaged_from_versioned_git_source -q` -> 155 passed.
- `uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py` -> pass.
- `cd web && npm run test -- --run tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx` -> 2 files passed, 23 tests passed.

Live runtime verification:

- `uv run parallax config` exited 0 and confirmed runtime config paths under `/Users/qinghuan/.parallax/`; no secret values were printed.
- Direct current-code `credit/stress` module probe through API-equivalent module history loading reported snapshot as-of `2026-06-16`, module status `ready`, diagnostics regime `contained` / `压力可控`, and rows for HY OAS, IG OAS, CCC-HY tail, `NFCI 金融条件`, and SLOOS. The live NFCI row reported current index `-0.5`, 1w/1m/3m changes `0.0`, adjusted index `-0.5`, and status label `条件稳定`, consistent with narrowing HY/IG spreads and neutral SLOOS.

## 2026-06-17 Continuation — HYG/LQD Credit ETF Relative Pressure

Red tests:

- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_credit_stress_module_read_adds_credit_diagnostics_from_history tests/unit/domains/macro_intel/test_macro_module_views.py::test_credit_stress_module_read_promotes_hyg_lqd_pressure_when_spreads_lag -q` initially failed because `credit_diagnostics.rows` omitted `HYG/LQD 信用 ETF` and a lagging HYG-vs-LQD history still produced the `contained` regime.
- `cd web && npm run test -- --run tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx` initially failed because the credit diagnostics formatter dropped ETF-relative rows, so the fixture's HYG/LQD row was not rendered.

Implementation notes:

- `credit/stress` now adds a `HYG/LQD 信用 ETF` row from existing `asset:hyg` and `asset:lqd` histories already retained in the credit module. The row reports HYG 1w/1m return, LQD 1w/1m return, relative HYG-minus-LQD performance, and status.
- Credit regime logic now promotes `credit_etf_pressure` when HYG underperforms LQD before HY/IG/CCC spreads fully confirm. Higher-severity HY/CCC credit stress and tail widening still take precedence. This keeps the row as a public ETF confirmation/contradiction signal, not a replacement for TRACE, ETF flow, ETF premium/discount, or licensed CDS.
- JNK was deliberately not added to `credit/stress` in this slice because HYG already supplies the high-yield ETF leg and JNK would duplicate the same public proxy without a distinct decision role.
- The web credit diagnostics model now formats ETF-relative rows as `HYG 1w ... · LQD 1w ... · 相对 ...`.

Green tests and checks:

- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_credit_stress_module_read_adds_credit_diagnostics_from_history tests/unit/domains/macro_intel/test_macro_module_views.py::test_credit_stress_module_read_promotes_hyg_lqd_pressure_when_spreads_lag -q` -> 2 passed.
- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/domains/macro_intel/test_macro_migration_contract.py tests/unit/test_api_macro_contract.py tests/architecture/test_project_structure.py::test_macrodata_cli_is_packaged_from_versioned_git_source -q` -> 156 passed.
- `uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py` -> pass.
- `cd web && npm run test -- --run tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx` -> 2 files passed, 23 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run lint` -> ESLint passed and architecture tests 13 files / 73 tests passed.

Live runtime verification:

- A read-only live fact probe against `~/.parallax/` found `asset:hyg`, `asset:lqd`, and `asset:jnk` projected as facts/read-model rows. `asset:hyg` and `asset:lqd` both had 83 points from `2026-02-17` to `2026-06-15`; `asset:jnk` had 82 points through `2026-06-12`. The product slice used HYG/LQD only to avoid duplicating the high-yield ETF proxy.
- Direct current-code `credit/stress` module probe through API-equivalent module history loading reported snapshot as-of `2026-06-16`, module status `ready`, diagnostics regime `contained` / `压力可控`, and rows for HY OAS, IG OAS, CCC-HY tail, `HYG/LQD 信用 ETF`, `NFCI 金融条件`, and SLOOS. The live HYG/LQD row reported HYG 1w `0.63%`, LQD 1w `0.86%`, relative 1w `-0.23%`, HYG 1m `1.25%`, LQD 1m `1.43%`, relative 1m `-0.19%`, and status label `ETF中性`, consistent with the contained credit regime.

## 2026-06-17 Continuation — Cross-Asset Diagnostics In Assets Landing

Red tests:

- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_assets_landing_module_read_adds_cross_asset_diagnostics_from_history -q` initially failed with `KeyError: 'asset_diagnostics'` because retained `assets` still produced chart/table evidence but no backend cross-asset diagnosis.
- `cd web && npm run test -- --run tests/component/features/macro/MacroModulePages.test.tsx` initially failed because the asset landing page had no accessible `跨资产诊断` region between `核心资产行情` and the support rail.

Implementation notes:

- Retained `assets` now emits backend `asset_diagnostics` from existing projected histories for SPX, TLT, DXY, WTI, BTC, VIX, and HY OAS. The payload includes row status labels, 1w/1m price changes or index/bp changes, cross-asset regime, summary, implication, and invalidation.
- The regime logic promotes `滞胀冲击` when equities and duration weaken while dollar and energy rise; otherwise it distinguishes `Risk-off`, `Risk-on`, and `分化` from the same backend facts. React only formats backend rows; it does not compute macro state.
- `MacroAssetOverviewPage` renders the generic `MacroSignalDiagnosticsPanel` as `跨资产诊断` directly after `核心资产行情`, so the asset page reads as market board -> decision read -> daily/data/correlation support. No deleted `assets/crypto-derivatives`, options/GEX, or compatibility route was restored.

Green tests and checks:

- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_assets_landing_module_read_adds_cross_asset_diagnostics_from_history -q` -> 1 passed.
- `cd web && npm run test -- --run tests/component/features/macro/MacroModulePages.test.tsx` -> 1 file passed, 12 tests passed.
- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/domains/macro_intel/test_macro_migration_contract.py tests/unit/test_api_macro_contract.py tests/architecture/test_project_structure.py::test_macrodata_cli_is_packaged_from_versioned_git_source -q` -> 157 passed.
- `uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py` -> pass.
- `cd web && npm run test -- --run tests/component/features/macro/MacroModulePages.test.tsx tests/unit/features/macro/model/macroWorkbenchModel.test.ts` -> 2 files passed, 23 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run lint` -> ESLint passed and architecture tests 13 files / 73 tests passed.

Live runtime verification:

- `uv run parallax config` confirmed runtime config paths `/Users/qinghuan/.parallax/config.yaml` and `/Users/qinghuan/.parallax/workers.yaml`; macrodata is enabled and FRED is configured. No secret values were printed.
- Direct current-code `assets` module probe through the same repository/view-builder path used by `/api/macro/modules/{module_id}` reported snapshot status `ready`, as-of `2026-06-16`, and `asset_diagnostics` regime `risk_on` / `Risk-on` with 7 rows.
- Live row evidence was SPX 1w `2.01%`, TLT 1w `1.3%`, DXY 1w `-0.42%`, WTI 1w `-11.56%`, BTC 1w `5.07%`, VIX current `16.2` / 1w `-2.7`, and HY OAS current `266.0bp` / 1w `-9.0bp`. The live summary was `跨资产主线偏 risk-on：权益和加密同步修复，美元与信用没有显著背离。`.

## 2026-06-17 Continuation — Equities Asset-Class Diagnostics

Red tests:

- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_equities_module_read_adds_asset_class_diagnostics_from_module_history -q` initially failed with `KeyError: 'asset_class_diagnostics'` because retained `assets/equities` still rendered chart/table evidence but no backend decision read.
- `cd web && npm run test -- --run tests/component/features/macro/MacroModulePages.test.tsx -t "renders asset-class normalized return page"` initially failed because the leaf page had no accessible `美股风险诊断` region between `主市场证据` and `驱动与反证`.

Implementation notes:

- Retained `assets/equities` now emits backend `asset_class_diagnostics` from existing projected module observations for SPX, NDX, RUT, QQQ, IWM, and `positioning:sp500_net_noncommercial`. The payload includes row status labels, 1w/1m price changes, CFTC positioning current/change rows, regime language, trade implication, and invalidation.
- The regime logic distinguishes `美股降温`, `广谱 risk-on`, `龙头收窄`, `仓位防守`, and `美股分化` from persisted Yahoo/CFTC histories. React only formats backend rows; it does not compute macro state or call providers.
- `MacroLeafModulePage` renders the generic `MacroSignalDiagnosticsPanel` as `美股风险诊断` directly after `主市场证据`. No deleted `assets/crypto-derivatives`, options/GEX, CFTC-only page, or hidden compatibility route was restored.

Green tests and checks:

- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_equities_module_read_adds_asset_class_diagnostics_from_module_history -q` -> 1 passed.
- `cd web && npm run test -- --run tests/component/features/macro/MacroModulePages.test.tsx -t "renders asset-class normalized return page"` -> 1 file passed, 1 test passed.
- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/test_api_macro_contract.py -q` -> 135 passed.
- `uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py` -> pass.
- `cd web && npm run test -- --run tests/component/features/macro/MacroModulePages.test.tsx tests/unit/features/macro/model/macroWorkbenchModel.test.ts` -> 2 files passed, 23 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run lint` -> ESLint passed and architecture tests 13 files / 73 tests passed.

Live runtime verification:

- Read-only live probe against `/Users/qinghuan/.parallax/config.yaml` and `/Users/qinghuan/.parallax/workers.yaml` reported snapshot status `ready`, facts max observed at `2026-06-16`, projection lag `0`, `assets/equities` health `partial`, and confidence `模块覆盖 15/15`.
- Direct current-code `assets/equities` module probe through the same repository/view-builder path used by `/api/macro/modules/{module_id}` reported `asset_class_diagnostics` present, regime label `广谱 risk-on`, 6 rows, and row labels `SPX`, `NDX`, `RUT`, `QQQ`, `IWM`, and `CFTC S&P 净投机`.
- Browser smoke on the current worktree Vite server at `127.0.0.1:5178` confirmed `/macro/assets/equities` routed and rendered `主市场证据` without console errors. The currently running local API process did not include this worktree's new backend payload, so that browser session did not display `美股风险诊断`; component tests and the direct current-code live probe are the authoritative UI/payload evidence for this slice.

## 2026-06-17 Continuation — Bonds Asset-Class Diagnostics

Red tests:

- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_bonds_module_read_adds_asset_class_diagnostics_from_module_history -q` initially failed with `KeyError: 'asset_class_diagnostics'` because retained `assets/bonds` still exposed bond ETF/OAS evidence as chart/table rows without a backend decision read.
- `cd web && npm run test -- --run tests/component/features/macro/MacroModulePages.test.tsx -t "renders bonds asset-class diagnostics"` initially failed because the generic asset-class panel kept the accessible region name `美股风险诊断` even when the backend payload label was `债券风险诊断`.

Implementation notes:

- Retained `assets/bonds` now emits backend `asset_class_diagnostics` from existing projected module observations for TLT, IEF, LQD, HYG, HY OAS, and IG OAS. The payload includes ETF 1w/1m price changes, OAS current/change rows, status labels, bond cross-section regime language, trade implication, and invalidation.
- The regime logic distinguishes `信用久期双压`, `久期修复`, `信用修复`, `久期承压`, and `债券分化` from persisted Yahoo/FRED histories. React formats backend rows only; it does not compute duration/credit state or call providers.
- `MacroLeafModulePage` now gives asset-class diagnostics their accessible region name from the backend payload label, so `assets/equities` remains `美股风险诊断` while `assets/bonds` renders as `债券风险诊断`. No standalone CDS page, old credit proxy shell, hidden route, or backward-compatible alias was restored.

Green tests and checks:

- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_bonds_module_read_adds_asset_class_diagnostics_from_module_history -q` -> 1 passed.
- `cd web && npm run test -- --run tests/component/features/macro/MacroModulePages.test.tsx -t "renders bonds asset-class diagnostics"` -> 1 file passed, 1 test passed.
- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/test_api_macro_contract.py -q` -> 136 passed.
- `uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py` -> pass.
- `cd web && npm run test -- --run tests/component/features/macro/MacroModulePages.test.tsx tests/unit/features/macro/model/macroWorkbenchModel.test.ts` -> 2 files passed, 24 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run lint` -> ESLint passed and architecture tests 13 files / 73 tests passed.
- `uv run python scripts/validate_sdd_artifacts.py` -> pass.

Live runtime verification:

- Read-only live probe against `/Users/qinghuan/.parallax/config.yaml` and `/Users/qinghuan/.parallax/workers.yaml` reported macrodata enabled and FRED configured without printing secret values.
- Direct current-code `assets/bonds` module probe through the same repository/view-builder path used by `/api/macro/modules/{module_id}` reported snapshot status `ready`, facts max observed at `2026-06-16`, projection lag `0`, `assets/bonds` health `ok`, and confidence `模块覆盖 10/10`.
- The same live probe reported `asset_class_diagnostics` present, regime label `久期修复`, 6 rows, and row labels `TLT`, `IEF`, `LQD`, `HYG`, `HY OAS`, and `IG OAS`.
- Browser smoke on the current worktree Vite server at `127.0.0.1:5179` opened `/macro/assets/bonds`; the browser session showed no frontend compile/runtime exception, but `/api` proxy calls returned 502 from the already-running service on port 8765, so the browser could not prove the new backend payload. Component tests and the direct current-code live probe are the authoritative UI/payload evidence for this slice.

## 2026-06-17 Continuation — Commodities Asset-Class Diagnostics

Red tests:

- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_commodities_module_read_adds_asset_class_diagnostics_from_module_history -q` initially failed with `KeyError: 'asset_class_diagnostics'` because retained `assets/commodities` still exposed commodity futures/ETF evidence as chart/table rows without a backend decision read.
- `cd web && npm run test -- --run tests/component/features/macro/MacroModulePages.test.tsx -t "renders commodities asset-class diagnostics"` passed on first run because the earlier generic asset-class panel already uses the backend payload label. No frontend production change was needed for commodities; the test remains as a regression that `商品冲击诊断` renders when the backend sends it.

Implementation notes:

- Retained `assets/commodities` now emits backend `asset_class_diagnostics` from existing projected module observations for WTI futures, Brent, NatGas futures, Gold futures, and Copper futures. The payload includes 1w/1m changes, commodity status labels, commodity regime language, trade implication, and invalidation.
- The regime logic distinguishes `能源通胀冲击`, `能源通胀缓和`, `防守金属`, `周期商品走强`, and `商品分化` from persisted Yahoo/FRED histories. React formats backend rows only; it does not compute commodity state or call providers.
- No commodity proxy shell, deleted route, new provider call, or backward-compatible alias was restored.

Green tests and checks:

- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_commodities_module_read_adds_asset_class_diagnostics_from_module_history -q` -> 1 passed.
- `cd web && npm run test -- --run tests/component/features/macro/MacroModulePages.test.tsx -t "renders commodities asset-class diagnostics"` -> 1 file passed, 1 test passed.
- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/test_api_macro_contract.py -q` -> 137 passed.
- `uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py` -> pass.
- `cd web && npm run test -- --run tests/component/features/macro/MacroModulePages.test.tsx tests/unit/features/macro/model/macroWorkbenchModel.test.ts` -> 2 files passed, 25 tests passed.

Live runtime verification:

- Read-only live probe against `/Users/qinghuan/.parallax/config.yaml` and `/Users/qinghuan/.parallax/workers.yaml` reported macrodata enabled and FRED configured without printing secret values.
- Direct current-code `assets/commodities` module probe through the same repository/view-builder path used by `/api/macro/modules/{module_id}` reported snapshot status `ready`, facts max observed at `2026-06-16`, projection lag `0`, `assets/commodities` health `partial`, and confidence `模块覆盖 13/13`.
- The same live probe reported `asset_class_diagnostics` present, regime label `商品分化`, 5 rows, and row labels `WTI`, `Brent`, `NatGas`, `Gold`, and `Copper`.

## 2026-06-17 Continuation — FX Asset-Class Diagnostics

Red tests:

- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_fx_module_read_adds_asset_class_diagnostics_from_module_history -q` initially failed with `KeyError: 'asset_class_diagnostics'` because retained `assets/fx` still exposed DXY, broad dollar, currency pairs, and UUP as chart/table rows without a backend decision read.
- `cd web && npm run test -- --run tests/component/features/macro/MacroModulePages.test.tsx -t "renders fx asset-class diagnostics"` passed on first run because the earlier generic asset-class panel already uses the backend payload label. No frontend production change was needed for FX; the test remains as a regression that `美元压力诊断` renders when the backend sends it.

Implementation notes:

- Retained `assets/fx` now emits backend `asset_class_diagnostics` from existing projected module observations for DXY, Broad USD, EURUSD, USDJPY, USDCNY, and UUP. The payload includes 1w/1m changes, currency-pair direction normalization, dollar-pressure status labels, regime language, trade implication, and invalidation.
- The regime logic distinguishes `美元挤压`, `美元回落`, `美元指数背离`, `美元回落背离`, and `外汇分化` from persisted FRED/Yahoo histories. React formats backend rows only; it does not compute FX state or call providers.
- No FX proxy shell, deleted route, new provider call, or backward-compatible alias was restored.

Green tests and checks:

- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_fx_module_read_adds_asset_class_diagnostics_from_module_history -q` -> 1 passed.
- `cd web && npm run test -- --run tests/component/features/macro/MacroModulePages.test.tsx -t "renders fx asset-class diagnostics"` -> 1 file passed, 1 test passed.
- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/test_api_macro_contract.py -q` -> 138 passed.
- `cd web && npm run test -- --run tests/component/features/macro/MacroModulePages.test.tsx tests/unit/features/macro/model/macroWorkbenchModel.test.ts` -> 2 files passed, 26 tests passed.
- `uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py` -> pass.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run lint` -> ESLint passed and architecture tests 13 files / 73 tests passed.
- `uv run python scripts/validate_sdd_artifacts.py` -> pass.
- `uv run python scripts/regen_sdd_work_index.py && uv run python scripts/regen_sdd_work_index.py --check` -> pass.
- `git diff --check` -> pass.

Live runtime verification:

- `uv run parallax config` with secret-safe filtering reported config path `/Users/qinghuan/.parallax/config.yaml` and workers config path `/Users/qinghuan/.parallax/workers.yaml`.
- Read-only live probe reported macrodata enabled and FRED configured without printing secret values.
- Direct current-code `assets/fx` module probe through the same repository/view-builder path used by `/api/macro/modules/{module_id}` reported snapshot status `ready`, facts max observed at `2026-06-16`, projection lag `0`, `assets/fx` health `ok`, and confidence `模块覆盖 14/14`.
- The same live probe reported `asset_class_diagnostics` present, regime label `外汇分化`, 6 rows, and row labels `DXY`, `Broad USD`, `EURUSD`, `USDJPY`, `USDCNY`, and `UUP`.

## 2026-06-17 Continuation — Crypto Asset-Class Diagnostics

Red tests:

- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_crypto_module_read_adds_asset_class_diagnostics_from_module_history -q` initially failed with `KeyError: 'asset_class_diagnostics'` because retained `assets/crypto` still exposed BTC and ETH as chart/table rows without a backend decision read.
- `cd web && npm run test -- --run tests/component/features/macro/MacroModulePages.test.tsx -t "renders crypto asset-class diagnostics"` passed on first run because the earlier generic asset-class panel already uses the backend payload label. No frontend production change was needed for crypto; the test remains as a regression that `加密 beta 诊断` renders when the backend sends it.

Implementation notes:

- Retained `assets/crypto` now emits backend `asset_class_diagnostics` from existing projected module observations for BTC and ETH. The payload includes 1w/1m changes, crypto beta status labels, regime language, trade implication, and invalidation.
- The regime logic distinguishes `加密 beta 降温`, `加密 beta 升温`, `BTC 单边修复`, `ETH 高 beta 追涨`, and `加密分化` from persisted Yahoo histories. React formats backend rows only; it does not compute crypto state or call providers.
- No `assets/crypto-derivatives` route, OKX/Deribit derivative shell, new provider call, or backward-compatible alias was restored.

Green tests and checks:

- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_crypto_module_read_adds_asset_class_diagnostics_from_module_history -q` -> 1 passed.
- `cd web && npm run test -- --run tests/component/features/macro/MacroModulePages.test.tsx -t "renders crypto asset-class diagnostics"` -> 1 file passed, 1 test passed.
- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/test_api_macro_contract.py -q` -> 139 passed.
- `cd web && npm run test -- --run tests/component/features/macro/MacroModulePages.test.tsx tests/unit/features/macro/model/macroWorkbenchModel.test.ts` -> 2 files passed, 27 tests passed.
- `uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py` -> pass.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run lint` -> ESLint passed and architecture tests 13 files / 73 tests passed.
- `uv run python scripts/validate_sdd_artifacts.py` -> pass.
- `uv run python scripts/regen_sdd_work_index.py && uv run python scripts/regen_sdd_work_index.py --check` -> pass.
- `git diff --check` -> pass.

Live runtime verification:

- `uv run parallax config` with secret-safe filtering reported config path `/Users/qinghuan/.parallax/config.yaml`, workers config path `/Users/qinghuan/.parallax/workers.yaml`, macrodata enabled, and FRED configured.
- Direct current-code `assets/crypto` module probe through the same repository/view-builder path used by `/api/macro/modules/{module_id}` reported snapshot status `ready`, facts max observed at `2026-06-16`, projection lag `0`, `assets/crypto` health `ok`, and confidence `模块覆盖 2/2`.
- The same live probe reported `asset_class_diagnostics` present, regime label `加密 beta 升温`, 2 rows, and row labels `BTC` and `ETH`.

## 2026-06-17 Continuation — Hard Delete Duplicate Fed Balance-Sheet Liquidity Page

Red tests:

- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_catalog.py::test_catalog_exposes_exact_supported_module_ids tests/unit/domains/macro_intel/test_macro_module_catalog.py::test_catalog_hard_deletes_proxy_only_modules tests/unit/domains/macro_intel/test_macro_module_catalog.py::test_rrp_tga_page_absorbs_public_market_operations_evidence -q` initially failed because `liquidity/fed-balance-sheet` was still in the backend catalog, did not raise `UnsupportedMacroModuleError`, and `liquidity/rrp-tga` did not yet absorb `liquidity:reserve_balances`.
- `cd web && npm run test -- --run tests/unit/features/macro/model/macroRoutes.test.ts` initially failed because `MACRO_MODULE_ROUTES` still contained `liquidity/fed-balance-sheet` and `parseMacroRouteTail("liquidity/fed-balance-sheet")` still returned an addressable module route.

Implementation notes:

- `liquidity/fed-balance-sheet` was removed from `MACRO_MODULE_IDS`, backend module configs, route labels, chart/table title labels, frontend module types, navigation tree, and responsive audit routes. No redirect, hidden shell, fixture route, or backward-compatible alias remains.
- `liquidity/rrp-tga` now owns the useful evidence that previously justified the duplicate page: `liquidity:fed_assets`, `liquidity:reserve_balances`, `liquidity:on_rrp`, `liquidity:tga`, secured funding rates, funding volumes, NY Fed RRP, and SRF. The product boundary is one live liquidity decision page, not two pages with overlapping balance-sheet facts.
- At this checkpoint the route registry still reported 17 addressable macro pages including `assets/correlation` while the backend module catalog reported 16 retained module ids; the later standalone-correlation cleanup below resolves that mismatch by hard-deleting `/macro/assets/correlation` and leaving correlation only as asset-page support data.

Green tests and checks:

- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_catalog.py::test_catalog_exposes_exact_supported_module_ids tests/unit/domains/macro_intel/test_macro_module_catalog.py::test_catalog_hard_deletes_proxy_only_modules tests/unit/domains/macro_intel/test_macro_module_catalog.py::test_rrp_tga_page_absorbs_public_market_operations_evidence -q` -> 3 passed.
- `cd web && npm run test -- --run tests/unit/features/macro/model/macroRoutes.test.ts` -> 1 file passed, 4 tests passed.
- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py tests/architecture/test_macro_no_compatibility_contract.py -q` -> 147 passed.
- `uv run ruff check src/parallax/domains/macro_intel/services/macro_module_catalog.py src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/domains/macro_intel/test_macro_module_views.py` -> pass.
- `cd web && npm run test -- --run tests/unit/features/macro/model/macroRoutes.test.ts tests/unit/features/macro/model/macroPageRegistry.test.ts tests/routes/macro.route.test.tsx tests/component/features/macro/MacroModulePages.test.tsx tests/component/features/cockpit/ui/AppSidebar.test.tsx` -> 5 files passed, 42 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run lint` -> ESLint passed and architecture tests 13 files / 73 tests passed.

Live runtime verification:

- Read-only live probe against `/Users/qinghuan/.parallax/config.yaml` and `/Users/qinghuan/.parallax/workers.yaml` reported module count `16`, `fed_balance_sheet_supported=False`, snapshot status `ready`, facts max observed at `2026-06-16`, projection lag `0`, and `liquidity/rrp-tga` with `data_health.summary_status=ok`.
- The same `liquidity/rrp-tga` live module view reported `confidence_label=模块覆盖 13/13`, `module_read.liquidity_diagnostics.rows=6`, tiles/table evidence for both `liquidity:fed_assets` and `liquidity:reserve_balances`, and no `/macro/liquidity/fed-balance-sheet` related route.
- Browser smoke on the current worktree Vite server at `127.0.0.1:5177` confirmed `/macro/liquidity/rrp-tga` navigation contains no `/macro/liquidity/fed-balance-sheet` link and direct `/macro/liquidity/fed-balance-sheet` renders the route-error surface instead of the deleted page. The two console errors observed were the expected React Router 404 render logs for the deleted direct route.

## 2026-06-17 Continuation — OKX/Deribit Crypto Derivatives Bundle

Source research:

- Official OKX public docs confirm REST endpoints for open interest, funding rate, mark price, and index tickers, with `oiUsd`, `fundingRate`, `markPx`, and `idxPx` fields suitable for BTC/ETH perp OI, funding, and basis evidence.
- Official Deribit public docs confirm ticker fields for perpetual `open_interest`, `funding_8h`, `mark_price`, and `index_price`, plus volatility-index candle data through `get_volatility_index_data`.

Red tests:

- `uv run pytest tests/unit/domains/macro_intel/test_macrodata_bundle_importer.py::test_import_macrodata_bundle_accepts_crypto_derivatives_core_without_page_shell tests/unit/test_worker_settings.py::test_default_workers_yaml_contains_canonical_worker_defaults tests/unit/domains/macro_intel/test_macro_sync_service.py::test_sync_service_enqueue_due_windows_schedules_all_configured_product_bundles -q` initially failed in the importer and worker-settings assertions because Parallax did not yet recognize the OKX/Deribit series keys or schedule `crypto-derivatives-core`.
- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_catalog.py::test_crypto_page_absorbs_okx_deribit_derivatives_after_derivatives_page_deletion -q` initially failed because retained `assets/crypto` only exposed BTC/ETH spot evidence.
- The first macrodata-cli provider test run failed on metric normalization for colon-delimited datasets before `_normalize_dataset(...)` was fixed in the OKX and Deribit providers.
- After macrodata-cli `0.1.21`, `uv run parallax macro sync --bundle crypto-derivatives-core --start 2026-06-16 --end 2026-06-17` failed with `macrodata_runner_error` because Parallax sync invokes `macrodata bundle history ...`, and `crypto-derivatives-core` had only a fetch surface. This drove the `0.1.22` follow-up adding `bundle history crypto-derivatives-core`.
- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_crypto_module_read_adds_derivatives_diagnostics_without_restoring_page -q` initially failed because retained `assets/crypto` still read the same source-backed OKX/Deribit rows as table evidence only and classified the module as spot-only `crypto_beta_risk_on`.
- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_crypto_module_data_health_marks_missing_derivatives_as_reference_gap -q` initially failed because spot-only `assets/crypto` rendered data health as `ok`, hiding the fact that derivatives OI/funding/basis/DVOL were absent.

Implementation notes:

- The external macrodata-cli checkout now has `OkxPublicDataProvider` and `DeribitPublicMarketProvider`, catalog entries, runtime wiring, a separate `CRYPTO_DERIVATIVES_CORE` bundle with 14 source-backed series, and a first-class `bundle history crypto-derivatives-core` command. The package version is bumped to `0.1.22`, committed/pushed at Git rev `dd86aa8bcd234e8fb427ba9d058e9b478e2a0e6c`, and Parallax `pyproject.toml` / `uv.lock` are repinned to that portable Git dependency.
- Parallax maps those 14 series to `crypto_derivatives:*` concept keys, marks them optional for long-history readiness, adds `crypto-derivatives-core` to default `workers.macro_sync.bundle_names`, and absorbs the rows into retained `assets/crypto` table evidence.
- Retained `assets/crypto` now also aggregates OKX+Deribit OI into BTC/ETH perp OI rows, averages OKX/Deribit funding and basis into bp rows, reads Deribit BTC/ETH DVOL, and uses those rows in the existing `asset_class_diagnostics` regime/implication/invalidation flow. Hot funding/rich basis/OI expansion/DVOL stress can downgrade a clean spot beta read into `crypto_leverage_chase`, `crypto_leverage_flush`, or `crypto_vol_stress`.
- When a retained `assets/crypto` view has spot BTC/ETH but no derivatives OI, funding, basis, or DVOL group, the module now surfaces warning-level `module_reference` gaps and reports `partial` instead of silently calling the page `ok`. This keeps source-health visible without turning optional derivatives into a blocking route or restoring a separate derivatives page.
- The deleted `assets/crypto-derivatives` route remains deleted. No hidden route, compatibility alias, page shell, frontend provider call, fake options surface, GEX field, or normalized-history placeholder was added.
- `parallax macro status` now partitions bundle expectations correctly: OKX/Deribit series are required under `crypto-derivatives-core`, not under `macro-core`.

Green tests and checks:

- `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest -q` -> 173 passed after the `0.1.22` history-command follow-up.
- `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run ruff check .` -> pass.
- `cd /Users/qinghuan/Documents/code/macrodata-cli && git push origin codex/macrodata-bls-calendar` pushed commits `03bb6a3d9e00850e56898e0a4f3216d36d03027b` and `dd86aa8bcd234e8fb427ba9d058e9b478e2a0e6c`.
- `uv run pytest tests/unit/domains/macro_intel/test_macrodata_bundle_importer.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/test_worker_settings.py tests/unit/domains/macro_intel/test_macro_sync_service.py tests/unit/test_cli_macro_commands.py -q` -> 148 passed.
- `uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/test_api_macro_contract.py -q` -> 142 passed after the retained crypto derivatives diagnostic and source-health slice.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run` -> 2 files passed, 28 tests passed.
- `uv run pytest tests/architecture/test_project_structure.py::test_macrodata_cli_is_packaged_from_versioned_git_source -q` -> 1 passed after updating the fixed expected Git rev to `dd86aa8bcd234e8fb427ba9d058e9b478e2a0e6c`.
- `uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_catalog.py` -> pass.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run lint` -> pass, including ESLint and 13 frontend architecture files / 73 tests.
- `uv run ruff check src/parallax/domains/macro_intel/_constants.py src/parallax/domains/macro_intel/services/macro_module_catalog.py src/parallax/platform/config/settings.py src/parallax/app/surfaces/cli/commands/macro.py tests/architecture/test_project_structure.py tests/unit/domains/macro_intel/test_macrodata_bundle_importer.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/test_worker_settings.py tests/unit/domains/macro_intel/test_macro_sync_service.py tests/unit/test_cli_macro_commands.py` -> pass.
- `uv run python scripts/validate_sdd_artifacts.py` -> pass.
- `uv run python scripts/regen_sdd_work_index.py && uv run python scripts/regen_sdd_work_index.py --check` -> pass.
- `git diff --check` -> pass.

Runtime status check:

- Before the current sandbox restriction, `uv run parallax macro status` exited 0 with installed macrodata-cli package version `0.1.22`, required series count `189`, missing required series count `0`, required bundle count `5`, missing required bundle count `0`, missing required bundle series count `0`, observations `83,488`, concept count `174`, history-ready `true`, latest snapshot `ready`, facts max observed at `2026-06-16`, and projection lag `0`.
- In the current restricted shell, `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run parallax macro status` still reports macrodata-cli `0.1.22`, all five required bundles available, and zero missing required bundle series before exiting with `OperationalError` on the configured Postgres host.
- In the current restricted shell, `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run macrodata bundle history crypto-derivatives-core --start 2026-06-16 --end 2026-06-17 --format json` reaches command `bundle.crypto-derivatives-core-history`, but OKX and Deribit provider requests return retryable `ConnectError` for all 14 series because outbound network/DNS is blocked in this session.
- In the current restricted shell, `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run parallax macro sync --bundle crypto-derivatives-core --start 2026-06-16 --end 2026-06-17` exits with `OperationalError` before provider import because the configured Postgres host is not reachable here. Unrestricted live sync/projection verification remains open; no compatibility shim or host-local fallback was added.

## 2026-06-17 Continuation — VIX Depth Source Health

Red tests:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_volatility_vix_data_health_marks_missing_implemented_depth_sources -q` initially failed because a VIX/VIX3M-only retained `volatility/vix` view emitted a valid `carry_contango` read but `data_health.module_gaps` was empty. The page could therefore look complete while missing implemented VIX1D/VIX9D, VVIX/SKEW, MOVE, and VIXY/VIXM depth evidence.

Implementation notes:

- `volatility/vix` now adds warning-level `module_reference` gaps for implemented depth groups that are entirely absent: `vol_event_premium_missing`, `vol_tail_depth_missing`, `vol_rates_vol_missing`, and `vol_futures_proxy_missing`.
- The gap logic is scoped only to the retained `volatility/vix` module and only to concepts already implemented in the catalog. Future CFE futures curve, realized-volatility, options-surface, and licensed ICE/Bloomberg depth remain SDD/tech-debt backlog items, not runtime page warnings.
- The deleted `volatility/dashboard` route remains deleted. No hidden route, compatibility alias, CFE futures placeholder, options-surface row, static backlog row, or frontend provider call was added.

Green tests and checks:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_volatility_vix_data_health_marks_missing_implemented_depth_sources -q` -> 1 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/test_api_macro_contract.py -q` -> 143 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_macro_no_compatibility_contract.py tests/unit/domains/macro_intel/test_macro_module_views.py::test_volatility_vix_data_health_marks_missing_implemented_depth_sources -q` -> 14 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py` -> pass.
- `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx --run` -> 1 file passed, 16 tests passed.
- `cd web && npm run test -- tests/unit/features/macro/model/macroRoutes.test.ts tests/routes/macro.route.test.tsx --run` -> 2 files passed, 18 tests passed.
- `cd web && npm run typecheck` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py && UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check && git diff --check` -> pass.

## 2026-06-17 Continuation — Credit Depth Source Health

Red tests:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_credit_stress_data_health_marks_missing_implemented_depth_sources -q` initially failed because a HY/IG/CCC/VIX retained `credit/stress` view emitted a valid `contained` read but `data_health.module_gaps` was empty. The page could therefore look complete while missing implemented HYG/LQD ETF pressure, NFCI financial conditions, SLOOS bank lending, and FRED loan-quality evidence.

Implementation notes:

- `credit/stress` now adds warning-level `module_reference` gaps for implemented depth groups that are absent or incomplete: `credit_etf_pressure_missing`, `credit_financial_conditions_missing`, `credit_bank_lending_missing`, and `credit_loan_quality_missing`.
- The gap logic is scoped only to the retained `credit/stress` module and only to concepts already implemented in the catalog/table/diagnostics surface. Future TRACE liquidity, ETF premium/discount/flows, and licensed CDS remain SDD/tech-debt backlog items, not runtime page warnings.
- The deleted `credit/cds` route remains deleted. No hidden route, compatibility alias, TRACE placeholder, ETF premium/discount row, licensed CDS proxy, static backlog row, or frontend provider call was added.

Green tests and checks:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_credit_stress_data_health_marks_missing_implemented_depth_sources -q` -> 1 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/test_api_macro_contract.py -q` -> 144 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_macro_no_compatibility_contract.py tests/unit/domains/macro_intel/test_macro_module_views.py::test_credit_stress_data_health_marks_missing_implemented_depth_sources -q` -> 14 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py` -> pass.
- `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx --run` -> 1 file passed, 16 tests passed.
- `cd web && npm run typecheck` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py && UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check && git diff --check` -> pass.

## 2026-06-17 Continuation — Policy Corridor Source Health

Red tests:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_fed_funds_data_health_marks_missing_implemented_corridor_depth_sources -q` initially failed because a target/EFFR/IORB/SOFR retained `rates/fed-funds` view emitted a valid `stable` policy read but `data_health.module_gaps` was empty. The page could therefore look complete while missing implemented DFF, SOFR 30D, OBFR, and EFFR/OBFR volume depth evidence.
- After adding the first source-depth gaps, `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/test_api_macro_contract.py -q` failed in `test_build_macro_module_view_returns_missing_v3_status_when_snapshot_is_absent` because snapshot-missing `rates/fed-funds` views appended policy depth gaps on top of the snapshot blocker. The repair made retained-page reference gaps run only when the module has a real snapshot.

Implementation notes:

- `rates/fed-funds` now adds warning-level `module_reference` gaps for implemented depth groups that are absent: `policy_daily_fed_funds_missing`, `policy_sofr_30d_missing`, `policy_unsecured_funding_missing`, and `policy_volume_depth_missing`.
- The gap logic is scoped only to the retained `rates/fed-funds` module and only to concepts already implemented in the catalog/table/diagnostics surface. Future FedWatch/meeting probabilities, FOMC text deltas, auction-tail data, and deeper subsurface funding remain SDD/tech-debt backlog items, not runtime page warnings.
- Snapshot-missing module views now keep the single `macro_view_snapshot_missing` blocker and skip module-reference source-depth gaps, so a missing read model is not mixed with optional source-health messaging.
- The deleted `rates/expectations`, Fed text, auction, and `liquidity/subsurface` routes remain deleted. No hidden route, compatibility alias, fake FedWatch probability, static backlog row, or frontend provider call was added.

Green tests and checks:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_fed_funds_data_health_marks_missing_implemented_corridor_depth_sources -q` -> 1 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_build_macro_module_view_returns_missing_v3_status_when_snapshot_is_absent tests/unit/domains/macro_intel/test_macro_module_views.py::test_fed_funds_data_health_marks_missing_implemented_corridor_depth_sources -q` -> 2 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/test_api_macro_contract.py -q` -> 145 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_macro_no_compatibility_contract.py tests/unit/domains/macro_intel/test_macro_module_views.py::test_fed_funds_data_health_marks_missing_implemented_corridor_depth_sources -q` -> 14 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py` -> pass.
- `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx tests/component/features/macro/MacroRatesWorkbench.test.tsx --run` -> 2 files passed, 28 tests passed.
- `cd web && npm run typecheck` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py && UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check && git diff --check` -> pass.

## 2026-06-17 Continuation — Liquidity Depth Source Health

Red tests:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_liquidity_rrp_tga_data_health_marks_missing_implemented_depth_sources -q` initially failed because an RRP/TGA-only retained `liquidity/rrp-tga` view emitted a valid `neutral` liquidity read but `data_health.module_gaps` was empty. The page could therefore look complete while missing implemented balance-sheet, secured-corridor, repo-depth, repo-volume, and NY Fed operations evidence.

Implementation notes:

- `liquidity/rrp-tga` now adds warning-level `module_reference` gaps for implemented depth groups that are absent: `liquidity_balance_sheet_missing`, `liquidity_secured_corridor_missing`, `liquidity_repo_depth_missing`, `liquidity_volume_depth_missing`, and `liquidity_nyfed_operations_missing`.
- The gap logic is scoped only to the retained `liquidity/rrp-tga` module and only to concepts already implemented in the catalog/table/diagnostics surface. Future OFR/STFM funding distributions, cross-currency basis, and global-dollar evidence remain SDD/tech-debt backlog items, not runtime page warnings.
- The deleted `liquidity/subsurface`, `liquidity/global-dollar`, duplicate balance-sheet routes, and generic liquidity operation routes remain deleted. No hidden route, compatibility alias, OFR/STFM placeholder, cross-currency-basis row, static backlog row, or frontend provider call was added.

Green tests and checks:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_liquidity_rrp_tga_data_health_marks_missing_implemented_depth_sources -q` -> 1 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/test_api_macro_contract.py -q` -> 146 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_macro_no_compatibility_contract.py tests/unit/domains/macro_intel/test_macro_module_views.py::test_liquidity_rrp_tga_data_health_marks_missing_implemented_depth_sources -q` -> 14 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py` -> pass.
- `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx --run` -> 1 file passed, 16 tests passed.
- `cd web && npm run typecheck` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py && UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check && git diff --check` -> pass.

## 2026-06-17 Continuation — Economy Depth Source Health

Red tests:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_inflation_data_health_marks_missing_implemented_depth_sources tests/unit/domains/macro_intel/test_macro_module_views.py::test_employment_data_health_marks_missing_implemented_depth_sources tests/unit/domains/macro_intel/test_macro_module_views.py::test_gdp_data_health_marks_missing_implemented_depth_sources -q` initially failed because CPI/Core/PPI-only `economy/inflation`, unemployment/payroll/claims-only `economy/employment`, and real-GDP-only `economy/gdp` retained views emitted valid diagnostic reads but `data_health.module_gaps` was empty.

Implementation notes:

- `economy/inflation` now adds warning-level `module_reference` gaps for implemented depth groups that are absent: `inflation_pce_missing`, `inflation_deflator_missing`, `inflation_market_expectations_missing`, and `inflation_consumer_expectations_missing`.
- `economy/employment` now adds warning-level `module_reference` gaps for implemented depth groups that are absent: `employment_job_openings_missing`, `employment_wage_missing`, and `employment_participation_missing`.
- `economy/gdp` now adds warning-level `module_reference` gaps for implemented depth groups that are absent: `growth_nominal_gdp_missing`, `growth_nowcast_missing`, `growth_production_housing_missing`, `growth_consumption_missing`, and `growth_consumer_depth_missing`.
- The gap logic is scoped only to retained economy modules and only to concepts already implemented in the catalog/table/diagnostics surface. Future actual-vs-consensus, prior, revision, release-surprise, and separate calendar/surprise read models remain SDD/tech-debt backlog items, not runtime page warnings.
- The deleted `economy/consumer` and separate economy calendar/surprise pages remain deleted. No hidden route, compatibility alias, actual/consensus/prior/revision placeholder, surprise row, static backlog row, or frontend provider call was added.

Green tests and checks:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_inflation_data_health_marks_missing_implemented_depth_sources tests/unit/domains/macro_intel/test_macro_module_views.py::test_employment_data_health_marks_missing_implemented_depth_sources tests/unit/domains/macro_intel/test_macro_module_views.py::test_gdp_data_health_marks_missing_implemented_depth_sources -q` -> 3 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/test_api_macro_contract.py -q` -> 149 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_macro_no_compatibility_contract.py tests/unit/domains/macro_intel/test_macro_module_views.py::test_inflation_data_health_marks_missing_implemented_depth_sources tests/unit/domains/macro_intel/test_macro_module_views.py::test_employment_data_health_marks_missing_implemented_depth_sources tests/unit/domains/macro_intel/test_macro_module_views.py::test_gdp_data_health_marks_missing_implemented_depth_sources -q` -> 16 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py` -> pass.
- `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx --run` -> 1 file passed, 16 tests passed.
- `cd web && npm run typecheck` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py && UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check && git diff --check` -> pass.

## 2026-06-17 Continuation — Rates Curve Source Health

Red tests:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_yield_curve_data_health_marks_missing_implemented_depth_sources tests/unit/domains/macro_intel/test_macro_module_views.py::test_real_rates_data_health_marks_missing_implemented_depth_sources -q` initially failed because a 2Y/10Y-only retained `rates/yield-curve` view and a 10Y-real-only retained `rates/real-rates` view emitted valid rates diagnostics but `data_health.module_gaps` was empty.

Implementation notes:

- `rates/yield-curve` now adds warning-level `module_reference` gaps for implemented depth groups that are absent: `yield_curve_front_end_missing`, `yield_curve_belly_missing`, `yield_curve_long_end_missing`, `yield_curve_real_rate_decomposition_missing`, and `yield_curve_breakeven_decomposition_missing`.
- `rates/real-rates` now adds warning-level `module_reference` gaps for implemented depth groups that are absent: `real_rates_tips_curve_missing`, `real_rates_breakeven_curve_missing`, and `real_rates_forward_inflation_missing`.
- The gap logic is scoped only to retained rates modules and only to concepts already implemented in the catalog/table/diagnostics surface. Future FedWatch/meeting probabilities, OIS, auction-tail data, Fed text deltas, and licensed rates feeds remain SDD/tech-debt backlog items, not runtime page warnings.
- The deleted `rates/auctions`, `rates/expectations`, and Fed text routes remain deleted. No hidden route, compatibility alias, fake meeting probability, OIS proxy, auction-tail row, static backlog row, or frontend provider call was added.

Green tests and checks:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_yield_curve_data_health_marks_missing_implemented_depth_sources tests/unit/domains/macro_intel/test_macro_module_views.py::test_real_rates_data_health_marks_missing_implemented_depth_sources -q` -> 2 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/test_api_macro_contract.py -q` -> 151 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_macro_no_compatibility_contract.py tests/unit/domains/macro_intel/test_macro_module_views.py::test_yield_curve_data_health_marks_missing_implemented_depth_sources tests/unit/domains/macro_intel/test_macro_module_views.py::test_real_rates_data_health_marks_missing_implemented_depth_sources -q` -> 15 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py` -> pass.
- `cd web && npm run test -- tests/component/features/macro/MacroRatesWorkbench.test.tsx tests/component/features/macro/MacroModulePages.test.tsx --run` -> 2 files passed, 28 tests passed.
- `cd web && npm run typecheck` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py && UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check && git diff --check` -> pass.

## 2026-06-17 Continuation — Asset Depth Source Health

Red tests:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_assets_landing_data_health_marks_missing_implemented_depth_sources tests/unit/domains/macro_intel/test_macro_module_views.py::test_equities_data_health_marks_missing_implemented_depth_sources tests/unit/domains/macro_intel/test_macro_module_views.py::test_bonds_data_health_marks_missing_implemented_depth_sources tests/unit/domains/macro_intel/test_macro_module_views.py::test_commodities_data_health_marks_missing_implemented_depth_sources tests/unit/domains/macro_intel/test_macro_module_views.py::test_fx_data_health_marks_missing_implemented_depth_sources -q` initially failed because core-only retained asset views emitted valid cross-asset or asset-class diagnostics while their implemented depth-source gaps were absent from `data_health.module_gaps`.

Implementation notes:

- Retained `assets` now adds warning-level `module_reference` gaps for missing risk breadth, duration proxy, credit stress, volatility, and commodity-depth confirmation.
- Retained `assets/equities` now adds warning-level `module_reference` gaps for missing growth leadership, small-cap breadth, global/sector proxies, and CFTC positioning.
- Retained `assets/bonds` now adds warning-level `module_reference` gaps for missing intermediate duration, inflation-protection proxy, credit beta, OAS spreads, and aggregate bond proxy.
- Retained `assets/commodities` now adds warning-level `module_reference` gaps for missing Brent, NatGas, precious-metals, copper, and commodity ETF proxies.
- Retained `assets/fx` now adds warning-level `module_reference` gaps for missing broad dollar, G10 pairs, Asia pairs, and FX ETF proxies. Retained `assets/crypto` continues to expose the existing OKX/Deribit derivative source-health gaps.
- The gap logic is scoped only to retained asset modules and only to concepts already implemented in the catalog/table/diagnostics surface. Future options/GEX, ETF flows, dealer positioning, standalone CFTC pages, and licensed asset feeds remain SDD/tech-debt backlog items, not runtime page warnings.
- The deleted `assets/crypto-derivatives`, standalone CFTC/options/GEX pages, CDS proxy pages, commodity proxy shells, and ETF-flow placeholders remain deleted or backlog-only. No hidden route, compatibility alias, options/GEX row, fake flow row, static backlog row, or frontend provider call was added.

Green tests and checks:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_assets_landing_data_health_marks_missing_implemented_depth_sources tests/unit/domains/macro_intel/test_macro_module_views.py::test_equities_data_health_marks_missing_implemented_depth_sources tests/unit/domains/macro_intel/test_macro_module_views.py::test_bonds_data_health_marks_missing_implemented_depth_sources tests/unit/domains/macro_intel/test_macro_module_views.py::test_commodities_data_health_marks_missing_implemented_depth_sources tests/unit/domains/macro_intel/test_macro_module_views.py::test_fx_data_health_marks_missing_implemented_depth_sources -q` -> 5 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/test_api_macro_contract.py -q` -> 156 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_macro_no_compatibility_contract.py tests/unit/domains/macro_intel/test_macro_module_views.py::test_assets_landing_data_health_marks_missing_implemented_depth_sources tests/unit/domains/macro_intel/test_macro_module_views.py::test_equities_data_health_marks_missing_implemented_depth_sources tests/unit/domains/macro_intel/test_macro_module_views.py::test_bonds_data_health_marks_missing_implemented_depth_sources tests/unit/domains/macro_intel/test_macro_module_views.py::test_commodities_data_health_marks_missing_implemented_depth_sources tests/unit/domains/macro_intel/test_macro_module_views.py::test_fx_data_health_marks_missing_implemented_depth_sources -q` -> 18 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py` -> pass.
- `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx tests/component/features/macro/MacroDataTable.test.tsx --run` -> 2 files passed, 23 tests passed.
- `cd web && npm run typecheck` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py && UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check && git diff --check` -> pass.

## 2026-06-17 Continuation — Standalone Asset Correlation Route Hard Delete

Red tests:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_catalog.py::test_catalog_hard_deletes_proxy_only_modules -q` initially failed because retained module `related_routes` still linked to `/macro/assets/correlation`.
- `cd web && npm run test -- tests/unit/features/macro/model/macroRoutes.test.ts tests/unit/features/macro/model/macroPageRegistry.test.ts tests/routes/macro.route.test.tsx tests/component/features/cockpit/ui/AppSidebar.test.tsx --run` initially failed because `assets/correlation` still parsed as a `matrix` route, the audit registry exposed 17 pages, the asset page linked to `相关性详情`, `/macro/assets/correlation` rendered `MacroMatrixPage`, and the sidebar still exposed the `相关性` leaf.

Implementation notes:

- `/macro/assets/correlation` is no longer an addressable frontend page. The `matrix` page kind, `routeKind="matrix"` branch, `MacroMatrixPage`, standalone page tests, breadcrumb target, sidebar child, and responsive product-route entry were deleted rather than hidden.
- Retained `assets` still fetches `/api/macro/assets/correlation` for its inline 60-day correlation evidence. This keeps the useful source-backed matrix while removing the redundant page layer.
- Backend `related_routes` for `assets` and `assets/equities` no longer link to `/macro/assets/correlation`; the catalog hard-delete test now treats `assets/correlation` like other proxy-only routes.
- Unused standalone correlation read/coverage/gap UI and CSS were removed with the route, so no dormant compatibility component remains.

Green tests and checks:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_catalog.py::test_catalog_hard_deletes_proxy_only_modules -q` -> 1 passed.
- `cd web && npm run test -- tests/unit/features/macro/model/macroRoutes.test.ts tests/unit/features/macro/model/macroPageRegistry.test.ts tests/unit/features/macro/model/macroCorrelationModel.test.ts tests/routes/macro.route.test.tsx tests/component/features/cockpit/ui/AppSidebar.test.tsx tests/component/features/macro/MacroShell.test.tsx --run` -> 6 files passed, 35 tests passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py tests/architecture/test_macro_no_compatibility_contract.py -q` -> 169 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/macro_intel/services/macro_module_catalog.py tests/unit/domains/macro_intel/test_macro_module_catalog.py` -> pass.
- `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx tests/component/features/macro/MacroDataTable.test.tsx tests/routes/macro.route.test.tsx tests/component/features/cockpit/ui/AppSidebar.test.tsx tests/unit/features/macro/model/macroRoutes.test.ts tests/unit/features/macro/model/macroPageRegistry.test.ts tests/unit/features/macro/model/macroCorrelationModel.test.ts tests/component/features/macro/MacroShell.test.tsx --run` -> 8 files passed, 58 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run lint` -> ESLint plus 13 frontend architecture files passed, 73 architecture tests passed.
- `cd web && npm run test:architecture` -> 13 files passed, 73 tests passed.
- `cd web && npm run test:e2e -- tests/e2e/golden-paths/macro-responsive-audit.spec.ts --project=desktop-1366` -> 1 Playwright test passed across the macro route/viewport audit. Vite logged `ws proxy error: read ECONNRESET` during teardown, but the responsive and hard-deleted route assertions passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py && UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check && git diff --check` -> pass.

## 2026-06-17 Continuation — Fed Communication Event Heatmap

Red tests:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_decision_console_adds_event_heatmap -q` failed because the expected `official_fed_text:speech_latest` policy-communication row was absent from `decision_console.event_heatmap`.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run` failed because the UI still exposed the old `14 天事件热力` section name after the fixture and tests were updated to the broader `事件热力` contract.

Implementation notes:

- `_event_heatmap` now accepts `fed_text` catalysts in addition to future 0-14 day official calendar and Treasury auction calendar catalysts.
- Fed text heatmap rows use `window=recent`, high severity for statements/minutes/press releases, medium severity for speeches, `category=policy`, `impact=fed_communication`, and the watch text `跟踪措辞、投票分歧和政策路径信号。`.
- The frontend decision console section is now labeled `事件热力`, with backend fields only; React still does not compute event severity, event categories, or macro impact.
- Deleted Fed statement/speech pages remain deleted. No route, hidden shell, hawk/dove text scoring, compatibility alias, or auction-result heatmap row was added.

Green tests and checks:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_decision_console_adds_event_heatmap -q` -> 1 passed.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run` -> 2 files passed, 28 tests passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_decision_console_adds_event_heatmap tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_event_heatmap_uses_untruncated_calendar_candidates tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_module_view_adds_official_event_catalysts_to_decision_console tests/unit/test_api_macro_contract.py::test_macro_overview_module_api_loads_event_concepts_for_decision_console -q` -> 4 passed.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx tests/routes/macro.route.test.tsx tests/unit/features/macro/model/macroRoutes.test.ts tests/unit/features/macro/model/macroPageRegistry.test.ts --run` -> 5 files passed, 49 tests passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/test_api_macro_contract.py tests/architecture/test_macro_no_compatibility_contract.py -q` -> 169 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py` -> pass.
- `cd web && npm run format:check` -> pass.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run lint` -> ESLint plus architecture tests passed, 13 files and 73 architecture tests passed.
- `cd web && npm run test:e2e -- tests/e2e/golden-paths/macro-responsive-audit.spec.ts --project=desktop-1366` -> 1 passed. Vite logged a teardown `ws proxy error: read ECONNRESET`, but the responsive-route assertions passed.

## 2026-06-17 Continuation — Overview Liquidity Pressure

Red tests:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_decision_console_adds_liquidity_pressure_from_retained_rrp_tga_diagnostics -q` failed with `KeyError: 'liquidity_pressure'` because overview `decision_console` did not yet reuse retained liquidity diagnostics.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run` failed because `buildMacroDecisionConsole(...)` did not expose `liquidityPressure` and the overview decision panel had no `流动性压力` region.

Implementation notes:

- Overview `_decision_console` now receives the module `feature_map`, calls the existing retained `_liquidity_diagnostics(...)`, and emits `liquidity_pressure` only when real liquidity history can produce diagnostics.
- `liquidity_pressure` includes a source-backed score/regime, summary, top drivers ordered by SOFR-IORB, net liquidity, TGA, RRP, repo-depth, and volume priority, plus the first implication and invalidation from the retained liquidity diagnostic.
- `MacroDecisionConsolePanel` renders `流动性压力` between `确认 / 背离` and `交易映射`. The frontend formats backend rows through the existing liquidity diagnostics row formatter and does not calculate liquidity score or regime.
- Deleted liquidity category aliases, transmission-chain, operations, reserves, global-dollar, and subsurface routes remain deleted. No hidden route, compatibility shell, frontend provider call, React-side liquidity scoring, or static placeholder warning was added.

Green tests and checks:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_decision_console_adds_liquidity_pressure_from_retained_rrp_tga_diagnostics -q` -> 1 passed.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run` -> 2 files passed, 29 tests passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/test_api_macro_contract.py tests/architecture/test_macro_no_compatibility_contract.py -q` -> 170 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py` -> pass.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx tests/routes/macro.route.test.tsx tests/unit/features/macro/model/macroRoutes.test.ts tests/unit/features/macro/model/macroPageRegistry.test.ts --run` -> 5 files passed, 50 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run format:check` -> pass after formatting `web/tests/component/features/macro/MacroModulePages.test.tsx`.
- `cd web && npm run lint` -> ESLint plus architecture tests passed, 13 files and 73 architecture tests passed.
- `cd web && npm run test:architecture` -> 13 files passed, 73 tests passed.
- `cd web && npm run test:e2e -- tests/e2e/golden-paths/macro-responsive-audit.spec.ts --project=desktop-1366` -> 1 Playwright macro responsive audit passed.

## 2026-06-17 Continuation — Overview Data Credibility Layer

Red tests:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_decision_console_adds_data_credibility_layer_from_core_features -q` failed with `KeyError: 'data_credibility'` because overview `decision_console` did not yet expose a source-backed data credibility table.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run` failed because `buildMacroDecisionConsole(...)` did not expose `dataCredibility` and the overview decision panel had no `数据可信度层` region.

Implementation notes:

- Overview `_decision_console` now emits `data_credibility` from retained core `feature_map` rows when enough core rows exist across cross-asset, dollar, crypto, commodity, rates, volatility, credit, and liquidity indicators.
- The backend block includes `label`, `issue_count`, `issue_label`, and rows with `concept_key`, short label, display value, unit label, observed date, source label, raw quality, and quality label. It reuses existing `_tile(...)` formatting and does not expose source series keys.
- `MacroDecisionConsolePanel` now renders `数据可信度层` instead of a generic blocker list. It shows issue count, core row value/source/as-of/quality, and existing quality blockers inside the same section.
- The frontend model prefers raw `observed_at` for compact as-of display and never computes source quality, data freshness, or issue counts in React.
- Deleted or weak macro routes remain deleted. No hidden route, compatibility shell, frontend provider call, React-side quality scoring, series-key leak, or static placeholder table was added.

Green tests and checks:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_decision_console_adds_data_credibility_layer_from_core_features -q` -> 1 passed.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run` -> 2 files passed, 30 tests passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/test_api_macro_contract.py tests/architecture/test_macro_no_compatibility_contract.py -q` -> 171 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py` -> pass.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/unit/features/macro/model/macroRoutes.test.ts tests/unit/features/macro/model/macroPageRegistry.test.ts tests/routes/macro.route.test.tsx tests/component/features/cockpit/ui/AppSidebar.test.tsx tests/component/features/macro/MacroModulePages.test.tsx tests/component/features/macro/MacroRatesWorkbench.test.tsx --run` -> 7 files passed, 72 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run format:check` -> pass after formatting `web/src/features/macro/ui/workbench/MacroDecisionConsolePanel.tsx`.
- `cd web && npm run lint` -> ESLint plus architecture tests passed, 13 files and 73 architecture tests passed.
- `cd web && npm run test:architecture` -> 13 files passed, 73 tests passed.
- `cd web && npm run test:e2e -- tests/e2e/golden-paths/macro-responsive-audit.spec.ts --project=desktop-1366` -> 1 Playwright macro responsive audit passed.

## 2026-06-17 Continuation — Overview Judgement Review

Red tests:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_decision_console_summarizes_judgement_review_across_holding_windows -q` failed because the old backend row still emitted `risk_down_credit_sensitive:1d` plus top-level 1D horizon/status/P&L fields instead of a multi-window `windows` payload.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run -t "judgement review"` failed because the frontend model returned `null` when the fixture carried the new windows-only row shape.

Implementation notes:

- Overview `_decision_console` now derives `judgement_review` from current `trade_map` rows after `_trade_map_item(...)` has attached source-backed `holding_period_review` evidence.
- Each review row uses all valid holding-period rows for a current trade expression, currently 1D/5D/20D, and carries the Trade Map historical trust summary. The old top-level 1D horizon/status/P&L row shape is removed rather than retained as compatibility.
- `MacroDecisionConsolePanel` renders `昨日判断复盘` immediately after `交易映射`, matching the TimSun-style trade then review loop while showing a compact multi-window summary and keeping the detailed holding-period block inside Trade Map.
- The frontend model formats only backend `windows` with existing P&L and signed-percent helpers; it does not infer trade status, recompute P&L, call providers, fabricate a previous-day LLM judgement, or fall back to old scalar fields.
- No deleted route, hidden compatibility shell, provider call, new persistence table, or static placeholder review was added.

Green tests and checks:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_decision_console_summarizes_judgement_review_across_holding_windows -q` -> 1 passed.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run` -> 2 files passed, 34 tests passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/architecture/test_macro_no_compatibility_contract.py -q` -> 107 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py` -> pass.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run format:check` -> initially failed on `tests/component/features/macro/MacroModulePages.test.tsx`; after `npx prettier --write tests/component/features/macro/MacroModulePages.test.tsx`, rerun passed.
- `cd web && npm run lint` -> ESLint plus architecture tests passed, 13 files and 73 architecture tests passed.
- `cd web && npm run test:architecture` -> 13 files passed, 73 tests passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check` -> pass.
- `git diff --check` -> pass.
- `rg -n "setdefault\\(\\\"remediation_hint\\\"|remediation_hint\\\"\\) or \\\"补齐数据源后重新投影。\\\"|def _remediation_hint|_remediation_hint\\(" src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py` -> no matches.
- `rg -n "\\\"data_gaps_json\\\": \\[\\{|snapshot\\[\\\"data_gaps_json\\\"\\] = \\[\\{|snapshot\\[\\\"data_gaps_json\\\"\\] = \\[\\{" tests/unit/domains/macro_intel/test_macro_module_views.py` -> no shorthand one-line mapped gap fixtures.
- `rg -n "get\\([^\\n]+\\\"(关注|中性|中|warning|macro)\\\"\\)|setdefault\\(\\\"severity\\\"|severity\\\"\\) or \\\"warning\\\"|_future_catalyst_severity\\(|node\\\"\\) or \\\"macro\\\"" src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py` -> no matches.

## 2026-06-17 Continuation — Asset Market Row Placeholder Hard Cut

Red tests:

- `cd web && npm run test -- tests/unit/features/macro/model/macroAssetOverviewModel.test.ts --run` failed because `buildAssetMarketGroups(...)` still kept rows whose latest value or name formatted to `暂无`.
- `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx --run -t "asset market rows"` failed because the asset market dashboard still rendered an IWM row without current price evidence.

Implementation notes:

- `buildAssetMarketGroups(...)` now drops asset market rows without a real display name or latest value.
- A follow-up red check added a malformed `fx:` row and failed until rows without a real symbol were also dropped.
- Asset market delta/date/source fields stay optional and no longer produce `暂无` or `缺少日期`.
- `AssetMarketDashboard` now returns `null` for empty groups and no longer carries a group-level `暂无...快照` row branch.

Green tests and checks:

- `cd web && npm run test -- tests/unit/features/macro/model/macroAssetOverviewModel.test.ts --run` -> 2 passed after the latest symbol fallback hard cut.
- `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx --run -t "asset market rows"` -> 1 passed, 33 skipped.
- `cd web && npx prettier --write src/features/macro/model/macroAssetOverviewTypes.ts src/features/macro/model/macroAssetOverviewModel.ts src/features/macro/ui/assets/AssetMarketDashboard.tsx tests/unit/features/macro/model/macroAssetOverviewModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx ../docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md ../docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md` -> all touched files unchanged.
- `cd web && npm run test -- tests/unit/features/macro/model/macroAssetOverviewModel.test.ts tests/component/features/macro/MacroDataTable.test.tsx tests/component/features/macro/MacroModulePages.test.tsx tests/component/features/macro/MacroRatesWorkbench.test.tsx --run` -> 4 files passed, 63 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run format:check` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture harness 13 files passed, 73 tests passed.
- `cd web && npm run test:e2e -- tests/e2e/golden-paths/macro-responsive-audit.spec.ts --project=desktop-1366` -> 1 Playwright macro responsive audit passed; existing Vite chunk-size warning observed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_macro_no_compatibility_contract.py -q` -> 16 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check` -> pass.
- `git diff --check` -> pass.

## 2026-06-17 Continuation — Asset Availability Empty Coverage Hard Cut

Red tests:

- `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx --run -t "asset availability"` failed because an empty `availability_proxy_notes` table still rendered a `覆盖` drawer.
- The same run failed because a partially populated asset availability row filled missing cells with `暂无`, and a placeholder-only row stayed in the coverage table.

Implementation notes:

- `AssetDiagnosticsBoard` now renders the `覆盖` drawer through an availability section that first builds displayable coverage rows.
- Coverage rows require a non-placeholder item label plus at least one real status/latest/coverage/notes value.
- Missing optional coverage cells render absent content instead of `暂无`; empty or placeholder-only rows are dropped.

Green tests and checks:

- `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx --run -t "asset availability"` -> 2 passed, 31 skipped.
- `cd web && npx prettier --write src/features/macro/ui/assets/AssetDiagnosticsBoard.tsx tests/component/features/macro/MacroModulePages.test.tsx ../docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md ../docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md` -> all touched files unchanged.
- `cd web && npm run test -- tests/unit/features/macro/model/macroAssetOverviewModel.test.ts tests/component/features/macro/MacroDataTable.test.tsx tests/component/features/macro/MacroModulePages.test.tsx tests/component/features/macro/MacroRatesWorkbench.test.tsx --run` -> 4 files passed, 61 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run format:check` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture harness 13 files passed, 73 tests passed.
- `cd web && npm run test:e2e -- tests/e2e/golden-paths/macro-responsive-audit.spec.ts --project=desktop-1366` -> 1 Playwright macro responsive audit passed; existing Vite chunk-size warning observed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_macro_no_compatibility_contract.py -q` -> 16 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check` -> pass.
- `git diff --check` -> pass.

## 2026-06-17 Continuation — Asset Correlation Empty Surface Hard Cut

Red tests:

- `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx --run` failed because a successful one-sided asset-correlation response still rendered an empty `负相关` group with `暂无`.
- The same run failed because a successful empty asset-correlation response kept the `60日相关性` section mounted instead of deleting the no-evidence surface.
- `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx --run -t "keeps asset correlation errors"` failed because the visible correlation error state still paired the error message with a no-data `暂无` meta label.

Implementation notes:

- `MacroAssetOverviewPage` now mounts the inline `60日相关性` support surface only while the correlation query is loading/erroring or when at least one available positive/negative pair exists.
- The correlation surface meta now renders `暂不可用` during error states instead of no-data copy.
- `AssetCorrelationPreview` now renders only populated pair groups and returns `null` for missing data instead of manufacturing `暂无相关性样本`.
- The retained `/api/macro/assets/correlation` query remains data plumbing for the asset landing page; no standalone route, compatibility shell, or CSS hiding was restored.

Green tests and checks:

- `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx --run` -> 30 passed.
- `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx --run -t "keeps asset correlation errors"` -> 1 passed, 30 skipped.
- `cd web && npx prettier --write src/features/macro/ui/pages/MacroAssetOverviewPage.tsx src/features/macro/ui/assets/AssetCorrelationPreview.tsx tests/component/features/macro/MacroModulePages.test.tsx ../docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md ../docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md` -> formatted `tests/component/features/macro/MacroModulePages.test.tsx` after the final error-state test; source and SDD files unchanged.
- `cd web && npm run test -- tests/unit/features/macro/model/macroAssetOverviewModel.test.ts tests/component/features/macro/MacroDataTable.test.tsx tests/component/features/macro/MacroModulePages.test.tsx tests/component/features/macro/MacroRatesWorkbench.test.tsx --run` -> 4 files passed, 59 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run format:check` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture harness 13 files passed, 73 tests passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_macro_no_compatibility_contract.py -q` -> 16 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check` -> pass.
- `git diff --check` -> pass.

## 2026-06-17 Continuation — Asset Market Empty Surface Hard Cut

Red test:

- `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx --run` failed because an asset landing module with an empty asset table still rendered `核心资产行情`, `项目 0`, five empty category rails, and `暂无...快照` rows.

Implementation notes:

- `buildAssetMarketGroups(...)` now filters out asset groups with zero rows.
- `MacroAssetOverviewPage` mounts `核心资产行情` only when the aggregate asset row count is positive.
- Cross-asset diagnostics, data-health, and correlation surfaces continue to render so the missing data path stays visible outside the empty market card.

Green tests and checks:

- `cd web && npm run test -- tests/unit/features/macro/model/macroAssetOverviewModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run` -> 2 files passed, 29 tests passed.
- `cd web && npx prettier --write src/features/macro/model/macroAssetOverviewModel.ts src/features/macro/ui/pages/MacroAssetOverviewPage.tsx tests/component/features/macro/MacroModulePages.test.tsx ../docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md ../docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md` -> all touched files unchanged.
- `cd web && npm run test -- tests/unit/features/macro/model/macroAssetOverviewModel.test.ts tests/component/features/macro/MacroDataTable.test.tsx tests/component/features/macro/MacroModulePages.test.tsx tests/component/features/macro/MacroRatesWorkbench.test.tsx --run` -> 4 files passed, 56 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture harness 13 files passed, 73 tests passed.
- `cd web && npm run format:check` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_macro_no_compatibility_contract.py -q` -> 16 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check` -> pass.
- `git diff --check` -> pass.

## 2026-06-17 Continuation — Leaf Market Evidence Empty Panel Hard Cut

Red test:

- `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx --run` failed because a leaf module with `primary_chart.series: []` and `tables: []` still rendered `主市场证据` with `unknown` and `暂无可绘制序列`.

Implementation notes:

- `MacroMarketBoard` now returns `null` only when both evidence channels are empty: no chart series seed and no supporting table rows.
- Leaf diagnostics and data-health panels continue to render, so missing evidence remains visible through repair/audit surfaces instead of an empty market card.

Green tests and checks:

- `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx --run` -> 27 passed.
- `cd web && npx prettier --write src/features/macro/ui/pages/MacroMarketBoard.tsx tests/component/features/macro/MacroModulePages.test.tsx ../docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md ../docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md` -> all touched files unchanged.
- `cd web && npm run test -- tests/component/features/macro/MacroDataTable.test.tsx tests/component/features/macro/MacroModulePages.test.tsx tests/component/features/macro/MacroRatesWorkbench.test.tsx --run` -> 3 files passed, 54 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture harness 13 files passed, 73 tests passed.
- `cd web && npm run format:check` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_macro_no_compatibility_contract.py -q` -> 16 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check` -> pass.
- `git diff --check` -> pass.

## 2026-06-17 Continuation — Rates Detail Empty Panel Hard Cut

Red test:

- `cd web && npm run test -- tests/component/features/macro/MacroRatesWorkbench.test.tsx --run` failed because a rates module with `tables: []` still rendered the `利率明细` panel with `0 张` and `暂无利率明细`.

Implementation notes:

- `RatesDetailTables` now returns `null` when no primary detail table has rows.
- Normal rates pages with primary table rows still render `利率明细` in the established workbench order.

Green tests and checks:

- `cd web && npm run test -- tests/component/features/macro/MacroRatesWorkbench.test.tsx --run` -> 19 passed.
- `rg -n "暂无利率明细" web/src/features/macro` -> no production matches.

## 2026-06-17 Continuation — Rates Primary Chart Empty Panel Hard Cut

Red test:

- `cd web && npm run test -- tests/component/features/macro/MacroRatesWorkbench.test.tsx --run` failed because a rates module with `primary_chart.series: []` still rendered `利率主图` with `暂无可绘制走廊数据`.

Implementation notes:

- `RatesPrimaryVisual` now returns `null` when the backend primary chart has no series seed.
- The hook order remains stable; the early return happens after the existing query/model hooks.
- Low-level chart primitives keep their accessible empty states for direct component use, but rates pages no longer mount a primary-chart card without source-backed chart seed data.

Green tests and checks:

- `cd web && npm run test -- tests/component/features/macro/MacroRatesWorkbench.test.tsx --run` -> 20 passed.
- `cd web && npx prettier --write src/features/macro/ui/rates/RatesPrimaryVisual.tsx tests/component/features/macro/MacroRatesWorkbench.test.tsx ../docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md ../docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md` -> all touched files unchanged.
- `cd web && npm run test -- tests/component/features/macro/MacroDataTable.test.tsx tests/component/features/macro/MacroModulePages.test.tsx tests/component/features/macro/MacroRatesWorkbench.test.tsx --run` -> 3 files passed, 53 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture harness 13 files passed, 73 tests passed.
- `cd web && npm run format:check` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_macro_no_compatibility_contract.py -q` -> 16 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check` -> pass.
- `git diff --check` -> pass.

## 2026-06-17 Continuation — Overview Future 24/72h Catalysts

Red tests:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_decision_console_adds_future_24_72h_catalysts -q` failed with `KeyError: 'future_catalysts'` because overview `decision_console` did not yet expose the short-window catalyst block.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run` failed because `buildMacroDecisionConsole(...)` did not expose `futureCatalysts` and the overview decision panel had no `未来 24/72h 催化剂` region.

Implementation notes:

- Overview `_decision_console` now emits `future_catalysts` as a backend-derived block with label `未来 24/72h 催化剂` and rows from explicit 24h/72h `scenario.watch_triggers` plus source-backed official calendar and Treasury auction calendar events inside the next three days.
- Event rows map 0-1 day windows to `24h` / high severity and 2-3 day windows to `72h` / medium severity. Events beyond three days and auction-result rows stay out of the short-window list.
- The frontend renders `futureCatalysts` after `流动性压力` and before `交易映射`, using only backend-provided labels, details, window labels, severity labels, source labels, and source URLs.
- Deleted calendar, auction, Fed text, and weak macro routes remain deleted. No hidden route, compatibility shell, frontend provider call, React-side catalyst scoring, auction-tail placeholder, or actual/consensus/surprise row was added.

Green tests and checks:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_decision_console_adds_future_24_72h_catalysts -q` -> 1 passed.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run` -> 2 files passed, 32 tests passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/test_api_macro_contract.py tests/architecture/test_macro_no_compatibility_contract.py -q` -> 173 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py` -> pass.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/unit/features/macro/model/macroRoutes.test.ts tests/unit/features/macro/model/macroPageRegistry.test.ts tests/routes/macro.route.test.tsx tests/component/features/cockpit/ui/AppSidebar.test.tsx tests/component/features/macro/MacroModulePages.test.tsx tests/component/features/macro/MacroRatesWorkbench.test.tsx --run` -> 7 files passed, 74 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run format:check` -> pass after formatting `web/src/features/macro/model/macroWorkbenchModel.ts` and `web/src/features/macro/ui/workbench/MacroDecisionConsolePanel.tsx`.
- `cd web && npm run lint` -> ESLint plus architecture tests passed, 13 files and 73 architecture tests passed.
- `cd web && npm run test:architecture` -> 13 files passed, 73 tests passed.
- `cd web && npm run test:e2e -- tests/e2e/golden-paths/macro-responsive-audit.spec.ts --project=desktop-1366` -> 1 Playwright macro responsive audit passed. Vite logged teardown `ws proxy error: read ECONNRESET`, but the responsive-route assertions passed.

## 2026-06-17 Continuation — Overview Three Most Important Changes Evidence

Red tests:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_scenario_engine.py::test_build_macro_scenario_derives_top_changes_from_feature_deltas_without_triggers -q` failed because feature-delta `top_changes` still only exposed `description`, `node`, and `kind`; structured change/latest/source/as-of/severity fields were absent.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run` failed because the frontend still rendered the old `重要变化` section title and used the plain description/meta instead of backend `evidence_label` plus severity.

Implementation notes:

- `macro_scenario_engine` now emits `change_label`, `value_label`, `observed_at`, `source_label`, `severity`, `severity_label`, and `evidence_label` for feature-delta `top_changes` rows.
- `macro_module_views._compact_signal(...)` preserves those display fields into `decision_console.top_changes` instead of dropping them during compacting.
- The Macro Workbench model prefers `evidence_label` for top-change detail and appends backend severity to the section meta. The decision-console component title is now `3 个最重要变化`.
- The frontend still does not rank changes, compute severity, call providers, or reconstruct source/as-of labels from raw features. Ranking and evidence remain backend-owned.

Green tests and checks:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_scenario_engine.py::test_build_macro_scenario_derives_top_changes_from_feature_deltas_without_triggers -q` -> 1 passed.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run` -> 2 files passed, 33 tests passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_scenario_engine.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/test_api_macro_contract.py tests/architecture/test_macro_no_compatibility_contract.py -q` -> 177 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/macro_intel/services/macro_scenario_engine.py src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_scenario_engine.py tests/unit/domains/macro_intel/test_macro_module_views.py` -> pass.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/unit/features/macro/model/macroRoutes.test.ts tests/unit/features/macro/model/macroPageRegistry.test.ts tests/routes/macro.route.test.tsx tests/component/features/cockpit/ui/AppSidebar.test.tsx tests/component/features/macro/MacroModulePages.test.tsx tests/component/features/macro/MacroRatesWorkbench.test.tsx --run` -> 7 files passed, 75 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run format:check` -> pass after formatting `web/tests/fixtures/macroFixture.ts`.
- `cd web && npm run lint` -> ESLint plus architecture tests passed, 13 files and 73 architecture tests passed.
- `cd web && npm run test:architecture` -> 13 files passed, 73 tests passed.
- `cd web && npm run test:e2e -- tests/e2e/golden-paths/macro-responsive-audit.spec.ts --project=desktop-1366` -> 1 Playwright macro responsive audit passed.

## 2026-06-17 Continuation — Overview Watchlist Alerts

Red tests:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_decision_console_adds_watchlist_alerts_from_trade_map_and_rules -q` failed with `KeyError: 'watchlist_alerts'` because overview `decision_console` did not yet expose the TimSun-style watchlist/trigger block.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run` failed because `buildMacroDecisionConsole(...)` had no `watchlistAlerts` model field and the overview panel still rendered the old `观察触发 / 失效条件` section.

Implementation notes:

- Overview `_decision_console` now emits `watchlist_alerts` with label `Watchlist 与触发提醒`, assets derived from current Trade Map legs, and rules derived from scenario watch triggers, scenario invalidations, and quality blockers.
- Watchlist rules carry backend-owned `kind`, `kind_label`, optional `window`, `severity`, and `severity_label`, so the frontend renders `触发 · 24h · 高`, `失效`, and `质量 · 阻断` without parsing raw evidence or recomputing severity.
- The Macro Workbench model deletes the old decision-console `watchTriggers` / `invalidations` fields and maps only `decision_console.watchlist_alerts` into `watchlistAlerts`. The panel replaces the old paired section with a single `Watchlist 与触发提醒` section after `事件催化`.
- Deleted macro routes and weak source pages remain hard-deleted. No hidden compatibility section, React-side trigger scoring, frontend provider call, or duplicate old watch/invalidations display was retained.

Green tests and checks:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_decision_console_adds_watchlist_alerts_from_trade_map_and_rules -q` -> 1 passed.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run` -> 2 files passed, 34 tests passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_scenario_engine.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/test_api_macro_contract.py tests/architecture/test_macro_no_compatibility_contract.py -q` -> 178 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py` -> pass.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run format:check` -> initially failed on `tests/component/features/macro/MacroModulePages.test.tsx`; after `npx prettier --write tests/component/features/macro/MacroModulePages.test.tsx`, `npm run format:check` passed.
- `cd web && npm run lint` -> ESLint plus architecture tests passed, 13 files and 73 architecture tests passed.
- `cd web && npm run test:architecture` -> 13 files passed, 73 tests passed.
- `cd web && npm run test:e2e -- tests/e2e/golden-paths/macro-responsive-audit.spec.ts --project=desktop-1366` -> 1 Playwright macro responsive audit passed.

## 2026-06-17 Continuation — Overview Structured Analysis Chain

Red tests:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_module_read_adds_structured_analysis_from_domain_diagnostics -q` failed with `KeyError: 'structured_analysis'` because overview `module_read` did not yet expose a cross-domain structured analysis block.
- `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx --run` failed because the overview page had no `跨域判断链` region between `今日决策台` and `跨域市场板`.

Implementation notes:

- Overview `_module_read(...)` now emits `structured_analysis` only for retained overview module views and only when existing domain diagnostics produce rows.
- `_structured_analysis(...)` reuses retained deterministic diagnostics for assets, yield curve, Fed policy, liquidity, growth, employment, inflation, volatility, and credit, then compresses each domain to label, regime label, summary fact, top evidence lines, trade implication, and invalidation.
- `buildMacroStructuredAnalysis(...)` maps the backend payload into the Macro Workbench model, and `MacroStructuredAnalysisPanel` renders `跨域判断链` after `今日决策台` and before `跨域市场板`.
- The frontend does not compute cross-domain scores, inspect raw features, call providers, or keep a hidden compatibility section.

Green tests and checks:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_module_read_adds_structured_analysis_from_domain_diagnostics -q` -> 1 passed.
- `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx --run` -> 1 file passed, 16 tests passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_scenario_engine.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/test_api_macro_contract.py tests/architecture/test_macro_no_compatibility_contract.py -q` -> 179 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py` -> pass.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run` -> 2 files passed, 34 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run format:check` -> pass after formatting `web/src/features/macro/model/macroWorkbenchModel.ts` and `web/tests/component/features/macro/MacroModulePages.test.tsx`.
- `cd web && npm run lint` -> ESLint plus architecture tests passed, 13 files and 73 architecture tests passed.
- `cd web && npm run test:architecture` -> 13 files passed, 73 tests passed.
- `cd web && npm run test:e2e -- tests/e2e/golden-paths/macro-responsive-audit.spec.ts --project=desktop-1366` -> 1 Playwright macro responsive audit passed.

## 2026-06-17 Continuation — Overview Structured Market Thesis

Red tests:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_module_read_adds_structured_analysis_from_domain_diagnostics -q` failed because `structured_analysis.rows` still started with `大类资产`; the expected first `市场主线` row from scenario/base-case data was absent.

Implementation notes:

- `_structured_analysis(...)` now receives the persisted scenario and prepends `_structured_market_thesis_row(...)` before domain diagnostic rows.
- The market-thesis row uses current regime label, base-case thesis/trade/invalidation, top-change evidence, and current Trade Map expression. Fallbacks use existing deterministic scenario invalidation and Trade Map labels, not frontend parsing.
- The structured-analysis row limit widened from 8 to 10 so the new market row does not squeeze out retained volatility or credit diagnostics when every domain has enough data.
- `MacroStructuredAnalysisPanel` needed no new logic: it renders the backend row like the other structured-analysis rows.

Green tests and checks:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_module_read_adds_structured_analysis_from_domain_diagnostics -q` -> 1 passed.
- `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx --run` -> 1 file passed, 16 tests passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_scenario_engine.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/test_api_macro_contract.py tests/architecture/test_macro_no_compatibility_contract.py -q` -> 179 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py` -> pass.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run` -> 2 files passed, 34 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run format:check` -> pass after formatting `web/tests/component/features/macro/MacroModulePages.test.tsx`.
- `cd web && npm run lint` -> ESLint plus architecture tests passed, 13 files and 73 architecture tests passed.
- `cd web && npm run test:architecture` -> 13 files passed, 73 tests passed.
- `cd web && npm run test:e2e -- tests/e2e/golden-paths/macro-responsive-audit.spec.ts --project=desktop-1366` -> 1 Playwright macro responsive audit passed.

## 2026-06-17 Continuation — Overview Fed Communication Structured Row

Red tests:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_structured_analysis_adds_fed_communication_from_official_text -q` failed with `IndexError` because `structured_analysis` had no `美联储沟通` row even when official Fed text observations were present.

Implementation notes:

- `_structured_analysis(...)` now receives observations and prepends `_structured_fed_communication_row(...)` after the market thesis row when `fed_text` event candidates are available.
- The row reuses `_event_catalyst_candidates(...)` and `_event_heatmap_classification(...)`, so it shares the same official Fed text parsing, document type, source, speaker, and watch text as the existing event catalyst/heatmap lanes.
- The row intentionally does not score hawk/dove stance. Fed text delta scoring remains a separate read-model/source task.
- `MacroStructuredAnalysisPanel` needed no new behavior; frontend fixture and component tests assert that backend `美联储沟通` rows render without React-side inference.

Green tests and checks:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_structured_analysis_adds_fed_communication_from_official_text -q` -> 1 passed.
- `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx --run` -> 1 file passed, 16 tests passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_scenario_engine.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/test_api_macro_contract.py tests/architecture/test_macro_no_compatibility_contract.py -q` -> 180 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py` -> pass.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run` -> 2 files passed, 34 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run format:check` -> pass.
- `cd web && npm run lint` -> ESLint plus architecture tests passed, 13 files and 73 architecture tests passed.
- `cd web && npm run test:architecture` -> 13 files passed, 73 tests passed.
- `cd web && npm run test:e2e -- tests/e2e/golden-paths/macro-responsive-audit.spec.ts --project=desktop-1366` -> 1 Playwright macro responsive audit passed; Vite logged the known teardown `ws proxy error: read ECONNRESET`, but the responsive-route assertions passed.

## 2026-06-17 Continuation — Overview Structured Analysis No Domain Drop

Red tests:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_structured_analysis_keeps_all_retained_domains -q` failed because `structured_analysis.rows[:10]` dropped the final `credit` row when market thesis, Fed communication, and all retained domain rows were present.

Implementation notes:

- `_structured_analysis(...)` no longer hard-truncates rows. The candidate set is bounded by the retained product domains, so no arbitrary cap is needed.
- The regression test monkeypatches every row producer to return a row and asserts the exact retained key order: market thesis, Fed communication, assets, rates, policy, liquidity, growth, employment, inflation, volatility, and credit.
- This is a hard-cut usability repair: complete data coverage must make the overview more complete, not hide the last domain.

Green tests and checks:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_structured_analysis_keeps_all_retained_domains -q` -> 1 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_scenario_engine.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/test_api_macro_contract.py tests/architecture/test_macro_no_compatibility_contract.py -q` -> 181 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py` -> pass after sorting the added import.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run` -> 2 files passed, 34 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run format:check` -> pass.
- `cd web && npm run lint` -> ESLint plus architecture tests passed, 13 files and 73 architecture tests passed.

## 2026-06-17 Continuation — Overview Structured Analysis Frontend No Domain Drop

Red tests:

- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts --run` failed because `buildMacroStructuredAnalysis(...)` still sliced rows to 8, dropping `inflation`, `volatility`, and `credit` from the complete retained-domain payload.
- `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx --run` failed because the overview fixture rendered only 6 structured-analysis domains and did not include the retained `美联储`, `经济增长`, `就业`, `通胀`, or `波动率` rows.

Implementation notes:

- Removed the frontend model-side `.slice(0, 8)` from `buildMacroStructuredAnalysis(...)`.
- Expanded the overview fixture's `structured_analysis.rows` to the full retained-domain order: market thesis, Fed communication, assets, rates, policy, liquidity, growth, employment, inflation, volatility, and credit.
- The component test now asserts the previously missing policy, growth, employment, inflation, and volatility evidence lines render in `跨域判断链`.
- The UI still renders backend payload only; no overflow bucket, compatibility alias, frontend provider call, or React-side domain scoring was added.

Green tests and checks:

- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts --run` -> 1 file passed, 19 tests passed.
- `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx --run` -> 1 file passed, 16 tests passed.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run` -> 2 files passed, 35 tests passed.
- `cd web && npm run format:check` -> pass after Prettier formatted `tests/component/features/macro/MacroModulePages.test.tsx`.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run lint` -> ESLint plus architecture tests passed, 13 files and 73 architecture tests passed.
- `cd web && npm run test:architecture` -> 13 files passed, 73 tests passed.
- `cd web && npm run test:e2e -- tests/e2e/golden-paths/macro-responsive-audit.spec.ts --project=desktop-1366` -> 1 Playwright macro responsive audit passed; the spec currently executes only on `desktop-1366`.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py && UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check` -> index regenerated and check passed.
- `git diff --check` -> pass.

## 2026-06-17 Continuation — Overview Market Event Flow Hard Cut

Red tests:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_module_view_adds_official_events_to_market_event_flow tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_event_flow_show_bls_release_time_and_reference_period tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_event_flow_prioritizes_near_upcoming_treasury_auction_calendar tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_market_event_flow_classifies_calendar_auction_and_fed_communication tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_market_event_flow_uses_untruncated_event_candidates -q` initially failed because overview events still lived under `decision_console.event_catalysts` / `decision_console.event_heatmap` and no sibling `market_event_flow` existed.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts --run` initially failed because `buildMacroMarketEventFlow` did not exist.
- `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx --run` initially failed because the overview page did not render a `市场事件流` region after `跨域判断链`.

Implementation notes:

- Overview `_module_read(...)` now emits sibling `module_read.market_event_flow` from the full source-backed event candidate set, while `_decision_console(...)` no longer emits `event_catalysts` or `event_heatmap`.
- `market_event_flow` includes official calendar, Treasury auction calendar/result, and Fed text rows with category, impact, window, severity, watch text, release timing/reference-period metadata, and primary-source URLs when present.
- The Macro Workbench model deletes old decision-console event fields and maps only `module_read.market_event_flow`; `MacroDecisionConsolePanel` no longer renders `事件热力` or `事件催化`.
- `MacroOverviewModulePage` renders `MacroMarketEventFlowPanel` after `MacroStructuredAnalysisPanel` and before the retained market board. This is a hard deletion of duplicated decision-console event lanes, not a hidden or compatibility fallback.

Green tests and checks:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_module_view_adds_official_events_to_market_event_flow tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_event_flow_show_bls_release_time_and_reference_period tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_event_flow_prioritizes_near_upcoming_treasury_auction_calendar tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_market_event_flow_classifies_calendar_auction_and_fed_communication tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_market_event_flow_uses_untruncated_event_candidates tests/unit/test_api_macro_contract.py::test_macro_overview_module_api_loads_event_concepts_for_market_event_flow -q` -> 6 passed.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run` -> 2 files passed, 34 tests passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_scenario_engine.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/test_api_macro_contract.py tests/architecture/test_macro_no_compatibility_contract.py -q` -> 181 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py` -> pass.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run format:check` -> pass.
- `cd web && npm run lint` -> ESLint plus 13 architecture files and 73 architecture tests passed.
- `cd web && npm run test:architecture` -> 13 files passed, 73 tests passed.
- `cd web && npm run test:e2e -- tests/e2e/golden-paths/macro-responsive-audit.spec.ts --project=desktop-1366` -> 1 Playwright macro responsive audit passed; the spec runs its own macro viewport matrix inside the desktop project.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py && UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check` -> index regenerated and check passed.
- `git diff --check` -> pass.

## 2026-06-17 Continuation — Overview News Event Flow

Red tests:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_market_event_flow_adds_source_backed_news_events -q` initially failed with `TypeError: build_macro_module_view() got an unexpected keyword argument 'news_rows'`.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_api_macro_contract.py::test_macro_overview_module_api_loads_news_rows_for_market_event_flow -q` initially failed because `/api/macro/modules/overview` never queried News Intel's page read model.

Implementation notes:

- `build_macro_module_view(...)` now accepts bounded `news_rows` and maps source-backed projected News rows into `module_read.market_event_flow` before official macro event rows.
- `/api/macro/modules/overview` reads News Intel through `NewsPageQuery(repository=repos.news).list_news(limit=6)` and passes those projected rows into the module-view builder.
- News event rows use `headline`, `summary`, `source_domain`, `canonical_url`, `latest_at_ms`, `market_scope`, `token_lanes`, and projected signal decision class to render source, date, asset tags, market-scope category, severity, and `改变主线 / 观察主线 / 不改主线`.
- The implementation does not read raw `news_items`, call news providers from the macro API, add frontend `/api/news` joins, or reintroduce old decision-console event fields.

Green tests and checks:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_market_event_flow_adds_source_backed_news_events -q` -> 1 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/test_api_macro_contract.py::test_macro_overview_module_api_loads_news_rows_for_market_event_flow -q` -> 1 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_market_event_flow_adds_source_backed_news_events tests/unit/test_api_macro_contract.py::test_macro_overview_module_api_loads_news_rows_for_market_event_flow -q` -> 2 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py -q` -> 132 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/app/surfaces/api/routes_macro.py src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/test_api_macro_contract.py` -> pass.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run` -> 2 files passed, 34 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run format:check` -> pass.
- `cd web && npm run lint` -> ESLint plus 13 architecture files and 73 architecture tests passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_scenario_engine.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/test_api_macro_contract.py tests/architecture/test_macro_no_compatibility_contract.py -q` -> 183 passed.
- `cd web && npm run test:architecture` -> 13 files passed, 73 tests passed.
- `cd web && npm run test:e2e -- tests/e2e/golden-paths/macro-responsive-audit.spec.ts --project=desktop-1366` -> 1 Playwright macro responsive audit passed; the spec runs its own macro viewport matrix inside the desktop project.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py` -> pass.

## 2026-06-17 Continuation — Actionable Data Health Gaps

Red tests:

- `cd web && npm run test -- tests/unit/features/macro/model/macroModulePresentation.test.ts -t "preserves actionable data-health gap remediation" --run` initially failed because `buildMacroDataHealthBuckets(...)` flattened the backend gap row to `["历史样本不足：无法计算 60 日变化"]`, dropping `remediation_hint`, severity, and scope.
- `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx -t "renders overview page grammar" --run` initially failed because `数据诊断` rendered only one-line gap chips and did not expose remediation copy such as `回填全局宏观历史后重新生成总览投影。`.

Implementation notes:

- `MacroDataHealthBucket.items` now contains structured items with `key`, `label`, `detail`, `severity`, and `scope`.
- Overview, leaf, asset, and rates diagnostics panels render gap rows as source-health repair lists instead of chip strings.
- Old macro health chip rendering/CSS classes were removed; no hidden compatibility display remains.
- `docs/CONTRACTS.md` now states the exact retained module ids and removes the stale `liquidity/fed-balance-sheet` contract residue.
- Runtime config diagnostic confirmed Parallax is reading `/Users/qinghuan/.parallax/config.yaml` and `/Users/qinghuan/.parallax/workers.yaml`; macrodata is enabled, FRED is configured via env name, and macrodata-cli `0.1.22` exposes all required bundles. `uv run parallax macro status` could not reach PostgreSQL in this session and returned `macro_status_unavailable` / `OperationalError`.

Green tests and checks:

- `cd web && npm run test -- tests/unit/features/macro/model/macroModulePresentation.test.ts -t "preserves actionable data-health gap remediation" --run` -> 1 passed.
- `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx -t "renders overview page grammar" --run` -> 1 passed.
- `rg -n "macro-rates-health-chip|macro-rates-health-chip-list|macro-workbench-chip|macro-assets-health-chip" web/src/features/macro web/tests -S` -> no matches.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run test -- tests/unit/features/macro/model/macroModulePresentation.test.ts tests/component/features/macro/MacroModulePages.test.tsx tests/component/features/macro/MacroRatesWorkbench.test.tsx --run` -> 3 files passed, 33 tests passed.
- `cd web && npm run format:check` -> pass.
- `cd web && npm run lint` -> ESLint plus 13 architecture files and 73 architecture tests passed.
- `cd web && npm run test:architecture` -> 13 files passed, 73 tests passed.
- `wc -l web/src/features/macro/ui/rates/macroRatesWorkbench.css web/src/features/macro/ui/rates/ratesDataHealthGaps.css web/src/features/macro/ui/workbench/macroWorkbench.css web/src/features/macro/ui/assets/macroAssetOverview.css` -> rates workbench 477 lines, rates gap CSS 43 lines, workbench CSS 452 lines, asset overview CSS 497 lines.
- `cd web && npm run build` -> TypeScript plus Vite production build passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py && UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check` -> index regenerated and check passed.
- `git diff --check` -> pass.
- `cd web && npm run test:e2e -- tests/e2e/golden-paths/macro-responsive-audit.spec.ts --project=desktop-1366` did not start because the current sandbox rejects local server binds: Vite preview failed with `listen EPERM: operation not permitted 127.0.0.1:4173`, and `python -m http.server 4187 --bind 127.0.0.1` failed with `PermissionError: [Errno 1] Operation not permitted`. No page assertion failed; the browser-server gate is environment-blocked in this session.

## Risks Observed

- Standalone macrodata-cli without `FRED_API_KEY` is too dependent on FRED public CSV and produced many timeout errors in the planning run; the new diagnostics expose this as provider health but do not replace the need for a configured FRED key in production.
- Local dev API startup still emits duplicate raw-frame persistence errors from GMGN WebSocket ingestion when anonymous frames repeat. This is a provider ingestion idempotency issue, not a macro Trade Map regression.
- Parallax live macro data is current and `ready` after the 3-year refresh.
  The snapshot still reports 5 honest quality gaps for stale/latest-window
  conditions; those should remain visible rather than hidden.
- Paid/institutional sources for SOFR futures, OIS, vol surface, CDS, detailed credit quality, OFR/STFM unsecured funding depth, cross-currency basis, and calendar-surprise data remain outside this feature.
- Parallax default `macro_sync` now schedules numeric `macro-core`, official event bundles, and `crypto-derivatives-core` from pinned macrodata-cli `0.1.22`. The remaining OKX/Deribit risk is operational verification in an unrestricted session with outbound provider access and reachable Postgres, plus stale-source checks, normalized history, and richer term/expiry structure.

## Follow-Ups

- Run retained primary child-route browser QA across desktop/mobile.
- Split paid/institutional data-source work into a separate SDD record after operator approval.

## 2026-06-17 Continuation — Source-Gated TimSun Gap Map

Implementation notes:

- Added `docs/references/MACRO_TIMSUN_SOURCE_GAP_MAP.md` with official-source
  references, fetch date 2026-06-17, current macrodata-cli baseline, gap matrix,
  restoration gates, and task breakdown.
- Updated `docs/TECH_DEBT.md` so the macro/timsun debt row points to the
  source-gated matrix rather than re-listing gaps without public/license/model
  classification.
- Updated `docs/references/README.md` and this SDD task log.
- This is a documentation/source-research slice only: no deleted route, module
  id, route alias, fixture, static future-source row, or compatibility code was
  added.

Green checks:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check` -> pass.
- `git diff --check` -> pass.
- `rg -n "static future-source|future source|hidden route|compatibility shell|fake FedWatch|CME FedWatch fixture|rates/expectations|liquidity/subsurface|credit/cds|assets/crypto-derivatives|volatility/dashboard" src/parallax web/src web/tests -S` -> only hard-deleted route negative tests and the architecture no-compatibility note matched; no new runtime route, fixture, hidden shell, or placeholder source row was added.

## 2026-06-17 Continuation — Economic Calendar Surprise Hard Cut

Red tests:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_event_flow_show_bls_release_time_and_reference_period tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_market_event_flow_classifies_calendar_auction_and_fed_communication -q` failed because official BLS/BEA calendar rows still emitted `impact=data_surprise`, `impact_label=数据波动`, and `watch=实际值、修正和市场预期差。` despite no source-backed consensus lane.

Implementation notes:

- `_event_flow_context(...)` now maps `official_calendar:bls*` and `official_calendar:bea*` rows to `impact=release_revision`, `impact_label=实际/修正`, and watch text `跟踪官方实际值、前值修正和数据口径变化。`.
- This is a deletion/rename of unsupported semantics only. It does not add actual/consensus/prior/revision placeholders, reopen a calendar/surprise route, or move consensus-surprise work out of the source-gated backlog.

Green tests and checks:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_event_flow_show_bls_release_time_and_reference_period tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_market_event_flow_classifies_calendar_auction_and_fed_communication -q` -> 2 passed.
- `rg -n "data_surprise|数据波动|市场预期差" src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py web/src/features/macro web/tests docs/references/MACRO_TIMSUN_SOURCE_GAP_MAP.md` -> no matches.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/architecture/test_macro_no_compatibility_contract.py -q` -> 107 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check` -> pass.
- `git diff --check` -> pass.

## 2026-06-17 Continuation — Auction Calendar Future-Source Copy Hard Cut

Red tests:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_market_event_flow_classifies_calendar_auction_and_fed_communication tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_module_view_adds_official_events_to_market_event_flow -q` failed because Treasury auction calendar rows still emitted `watch=拍卖需求和交割日资金占用；auction tail 未接入。`.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts --run -t "labels missing provenance"` failed because missing provenance rendered `来源待接入` instead of an absent-source label.

Implementation notes:

- `_event_flow_context(...)` now maps `auction_calendar` rows to `关注拍卖需求、公告规模和交割日资金占用。`, which is limited to the official calendar/result context Parallax actually carries.
- The overview fixture removes the stale `未来宏观日历待接入` future-integration gap and component assertions for `接入官方日历 bundle 后重新投影。`.
- Macro fixture status labels for missing SOFR coverage now say `缺失` instead of `待接入`; the interim absent-source label was later replaced by the Source Detail hard cut with `0 个来源`.
- Auction tail remains only in the source-gated gap map because it requires an approved when-issued yield source and formula tests.

Green tests and checks:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_market_event_flow_classifies_calendar_auction_and_fed_communication tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_module_view_adds_official_events_to_market_event_flow -q` -> 2 passed.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run` -> 2 files passed, 35 tests passed.
- `rg -n "auction tail 未接入|未来宏观日历待接入|接入官方日历 bundle|SOFR 30D 待接入|来源待接入|status_label: \"待接入\"|未接入|待接入" src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py web/tests/fixtures/macroFixture.ts web/tests/unit/features/macro/model/macroWorkbenchModel.test.ts web/tests/component/features/macro/MacroModulePages.test.tsx web/src/features/macro` -> no matches.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/architecture/test_macro_no_compatibility_contract.py -q` -> 107 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py` -> pass.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run format:check` -> pass.
- `cd web && npm run lint` -> ESLint plus 13 architecture files and 73 architecture tests passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check` -> pass.

## 2026-06-17 Continuation — Data Gap Placeholder Hard Cut

Red tests:

- `cd web && npm run test -- tests/unit/features/macro/model/macroPageViewModel.test.ts --run -t "uses display-ready v3 labels"` failed because `gapLabel("insufficient_history:60d")` still returned `数据缺口待确认`.
- `cd web && npm run test -- tests/unit/features/macro/model/macroModulePresentation.test.ts --run -t "code-only"` failed because a completely unlabeled `{}` gap rendered as `未标注数据缺口` instead of being filtered out.

Implementation notes:

- `gapLabel(...)` now derives display labels from real gap codes after checking backend display fields.
- Known code shapes such as `insufficient_history:<window>`, `stale_latest:<window>`, and `*_missing` render as display-ready labels.
- `buildMacroDataHealthBuckets(...)` keeps code-only gaps but drops fully unlabeled and uncoded objects.
- The frontend no longer contains the `数据缺口待确认` placeholder in macro presentation/model/test/fixture scope.

Green tests and checks:

- `cd web && npm run test -- tests/unit/features/macro/model/macroPageViewModel.test.ts tests/unit/features/macro/model/macroModulePresentation.test.ts --run` -> 2 files passed, 14 tests passed.
- `rg -n "数据缺口待确认" web/src/features/macro web/tests/unit/features/macro web/tests/component/features/macro web/tests/fixtures/macroFixture.ts` -> no matches.
- `cd web && npm run test -- tests/unit/features/macro/model/macroPageViewModel.test.ts tests/unit/features/macro/model/macroModulePresentation.test.ts tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx tests/component/features/macro/MacroRatesWorkbench.test.tsx --run` -> 5 files passed, 49 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run format:check` -> pass.
- `cd web && npm run lint` -> ESLint plus 13 architecture files and 73 architecture tests passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check` -> pass.
- `git diff --check` -> pass.
- `git diff --check` -> pass.

## 2026-06-17 Continuation — Future Integration Contract Hard Delete

Red tests:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_build_macro_module_view_projects_v3_display_contract -q` failed because `data_health` still exposed the empty legacy future-source bucket.
- `cd web && npm run test -- tests/unit/features/macro/model/macroModulePresentation.test.ts --run` failed because `buildMacroDataHealthBuckets(...)` still returned the `future_integration_gaps` bucket.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_catalog.py::test_catalog_has_no_static_source_backlog_gap_codes -q` failed because `MacroModuleConfig` still had the empty `gap_codes` compatibility slot.

Implementation notes:

- `_data_health(...)` now returns only `module_gaps`, `chart_gaps`, and `global_gaps`.
- Generic `_module_evidence(...)` no longer builds watch triggers from static future-source rows.
- `MacroModuleConfig.gap_codes` and every empty `gap_codes=()` initializer were removed.
- Frontend contracts, fixtures, diagnostics bucket builders, rates/page view-model gap aggregation, and diagnostic scope labels no longer declare or consume the future-source bucket.

Green tests and checks:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_build_macro_module_view_projects_v3_display_contract tests/unit/domains/macro_intel/test_macro_module_catalog.py::test_catalog_has_no_static_source_backlog_gap_codes -q` -> 2 passed.
- `cd web && npm run test -- tests/unit/features/macro/model/macroModulePresentation.test.ts --run` -> 1 file passed, 5 tests passed.
- `rg -n "future_integration_gaps|future_integration|未来集成" src/parallax web/src web/tests tests/unit/domains/macro_intel tests/unit/test_api_macro_contract.py tests/architecture/test_macro_no_compatibility_contract.py` -> only the backend absence assertion remains.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/architecture/test_macro_no_compatibility_contract.py -q` -> 141 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py src/parallax/domains/macro_intel/services/macro_module_catalog.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_catalog.py` -> pass.
- `cd web && npm run test -- tests/unit/features/macro/model/macroModulePresentation.test.ts tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts tests/unit/features/macro/model/macroPageViewModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx tests/component/features/macro/MacroRatesWorkbench.test.tsx --run` -> 5 files passed, 48 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run format:check` -> pass after Prettier formatted the touched TS files.
- `cd web && npm run lint` -> ESLint plus 13 architecture files and 73 architecture tests passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check` -> pass.

## 2026-06-17 Continuation — Decision Console Metadata Placeholder Hard Cut

Red tests:

- `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx --run -t "omits missing decision-console metadata"` failed because missing scenario probability and Trade Map metadata still rendered `概率待确认`, `窗口待确认`, `确认：待确认`, and `失效：待确认`.

Implementation notes:

- `MacroDecisionConsolePanel` now omits missing scenario meta, trade windows, confirmation rows, and invalidation rows instead of rendering fallback copy.
- `MacroDecisionTradeMapItem.confirms` and `.invalidates` are nullable model fields.
- `codeList(...)` returns `null` for missing or unmapped arrays, `signalLabel(...)` no longer returns `待确认信号`, and `tradeExpressionLabel(...)` no longer returns `待确认交易映射`.
- `tradeMapItem(...)` now prefers backend display labels and drops unknown English trade expressions that lack a display label.

Green tests and checks:

- `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx --run -t "omits missing decision-console metadata"` -> 1 passed, 16 skipped.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts --run` -> 20 passed.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run` -> 2 files passed, 37 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run format:check` -> pass.
- `cd web && npm run lint` -> ESLint plus 13 architecture files and 73 architecture tests passed.
- `rg -n "概率待确认|窗口待确认|确认：待确认|失效：待确认|待确认信号|待确认交易映射" web/src/features/macro web/tests/component/features/macro/MacroModulePages.test.tsx web/tests/unit/features/macro/model/macroWorkbenchModel.test.ts web/tests/fixtures/macroFixture.ts` -> production code has no matches; only negative test assertions remain.

## 2026-06-17 Continuation — Backend Signal Placeholder Hard Cut

Red tests:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_module_view_omits_unmapped_signal_and_trade_placeholder_copy -q` failed because overview module evidence still rendered an unmapped confirmation as `label=待确认信号`.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_scenario_engine.py::test_build_macro_scenario_omits_unmapped_trigger_placeholder_labels -q` failed because the scenario engine kept an unmapped trigger in `confirmations`.

Implementation notes:

- `_code_label(...)` in both macro scenario and module-view builders now returns `None` for unknown English codes instead of `待确认信号`; explicit CJK display text remains displayable.
- Overview module evidence, top changes, future catalysts, watchlist rules, structured-analysis signal lines, and scenario trigger summaries filter unmapped codes out of display lists.
- `_trade_map_expression_label(...)` returns `None` for unknown expressions; module views drop unknown English Trade Map expressions without backend labels instead of returning `待确认交易映射`.
- `global_term_premium` is now an explicit backend signal label rather than falling through a generic placeholder path.

Green tests and checks:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_module_view_omits_unmapped_signal_and_trade_placeholder_copy -q` -> 1 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_scenario_engine.py::test_build_macro_scenario_omits_unmapped_trigger_placeholder_labels -q` -> 1 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/domains/macro_intel/test_macro_scenario_engine.py -q` -> 100 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py src/parallax/domains/macro_intel/services/macro_scenario_engine.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/domains/macro_intel/test_macro_scenario_engine.py` -> pass.
- `rg -n "待确认信号|待确认交易映射" src/parallax/domains/macro_intel/services/macro_module_views.py src/parallax/domains/macro_intel/services/macro_scenario_engine.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/domains/macro_intel/test_macro_scenario_engine.py web/src/features/macro web/tests/unit/features/macro web/tests/component/features/macro web/tests/fixtures/macroFixture.ts` -> production code has no matches; only negative test assertions remain.

## 2026-06-17 Continuation — Backend Diagnostics Pending Status Hard Cut

Red tests:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_asset_diagnostics_marks_single_point_rows_as_insufficient_history -q` failed because single-point TLT/BTC rows still emitted `status=unknown`, `status_label=待确认`.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_liquidity_diagnostics_marks_single_point_volume_as_insufficient_history tests/unit/domains/macro_intel/test_macro_module_views.py::test_volatility_diagnostics_marks_single_point_front_etf_as_insufficient_history -q` failed because SOFR volume and VIXY/VIXM rows still emitted `status=unknown`.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_backend_status_fallbacks_use_specific_insufficient_history_labels -q` failed because `_structured_regime_label({})` still returned `待确认`.

Implementation notes:

- Asset/FX price rows with current values but no 1w/1m change window now emit `insufficient_history` / `样本不足`.
- SOFR volume, net liquidity, VIXY/VIXM, VIX term/premium helpers, and structured-analysis regime fallback now use explicit `样本不足` instead of `待确认`.
- Judgement Review windows map missing status metadata to `insufficient_history` / `样本不足`, while preserving explicit backend status labels when present.

Green tests and checks:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_asset_diagnostics_marks_single_point_rows_as_insufficient_history tests/unit/domains/macro_intel/test_macro_module_views.py::test_liquidity_diagnostics_marks_single_point_volume_as_insufficient_history tests/unit/domains/macro_intel/test_macro_module_views.py::test_volatility_diagnostics_marks_single_point_front_etf_as_insufficient_history tests/unit/domains/macro_intel/test_macro_module_views.py::test_backend_status_fallbacks_use_specific_insufficient_history_labels -q` -> 4 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/domains/macro_intel/test_macro_scenario_engine.py -q` -> 104 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py` -> pass.
- `rg -n "待确认" src/parallax/domains/macro_intel/services/macro_module_views.py src/parallax/domains/macro_intel/services/macro_scenario_engine.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/domains/macro_intel/test_macro_scenario_engine.py` -> production code has no matches; only negative test assertions remain.

## 2026-06-17 Continuation — Backend Gap Payload Label Derivation Hard Cut

Red tests:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_gap_payloads_do_not_preserve_labels_for_retired_source_backlog_codes tests/unit/domains/macro_intel/test_macro_module_views.py::test_gap_payloads_do_not_preserve_labels_for_implemented_source_gaps -q` failed because gap payloads still used `数据缺口：待补齐数据源` for unmapped missing-source codes.

Implementation notes:

- `macro_gap_payloads._gap_label(...)` no longer has a generic backlog fallback.
- Known missing-source codes now map to explicit Chinese labels, including MOVE, basis, VIX term structure, Fed calendar/speeches/statement text, crypto options, ETF flows, equity breadth/options GEX, SLOOS, loan quality, JOLTS, average hourly earnings, and personal spending.
- Unknown code-bearing gaps derive a readable code label rather than preserving a compatibility placeholder.

Green tests and checks:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_gap_payloads_do_not_preserve_labels_for_retired_source_backlog_codes tests/unit/domains/macro_intel/test_macro_module_views.py::test_gap_payloads_do_not_preserve_labels_for_implemented_source_gaps -q` -> 2 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py -q` -> 99 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/macro_intel/services/macro_gap_payloads.py tests/unit/domains/macro_intel/test_macro_module_views.py` -> pass.
- `rg -n "待确认|待接入|未接入|数据缺口：待补齐数据源|待补齐数据源" src/parallax/domains/macro_intel/services web/src/features/macro` -> production code had only frontend asset overview `待确认` matches before the next cleanup slice.

## 2026-06-17 Continuation — Asset Overview Pending Placeholder Hard Cut

Red tests:

- `cd web && npm run test -- tests/unit/features/macro/model/macroAssetOverviewModel.test.ts --run` failed because asset rows without date/source evidence returned `asOf=待确认` and `quality=待确认`.
- `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx --run -t "does not render pending placeholders when asset snapshot metadata is absent"` failed because the asset page rendered `待确认` in the snapshot stat, row quality chips, row date cells, and daily-brief coverage metrics.

Implementation notes:

- `AssetMarketRow.asOf` and `.quality` are nullable display fields now.
- `buildAssetMarketGroups(...)` returns `null` when there is no real row as-of or source/quality evidence.
- `MacroAssetOverviewPage` omits the page-level `截至` stat when the snapshot has no real as-of label.
- `AssetMarketDashboard` displays `缺少日期` for missing row dates and omits absent source-quality chips.
- `AssetDailyBrief` displays `样本不足` for missing coverage ratios and missing gap counts instead of `待确认` or fake `0`.

Green tests and checks:

- `cd web && npm run test -- tests/unit/features/macro/model/macroAssetOverviewModel.test.ts --run` -> 1 passed.
- `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx --run -t "does not render pending placeholders when asset snapshot metadata is absent"` -> 1 passed, 17 skipped.
- `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx --run` -> 18 passed.
- `rg -n "待确认|待接入|未接入|数据缺口：待补齐数据源|待补齐数据源" src/parallax/domains/macro_intel/services web/src/features/macro web/tests/unit/features/macro web/tests/component/features/macro | head -120` -> production code has no matches; only negative test assertions remain.

Final checks for the backend gap-label and asset-overview placeholder slices:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py -q` -> 99 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/macro_intel/services/macro_gap_payloads.py tests/unit/domains/macro_intel/test_macro_module_views.py` -> pass.
- `cd web && npm run test -- tests/unit/features/macro/model/macroAssetOverviewModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run` -> 2 files passed, 19 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run format:check` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture harness 13 files passed, 73 tests passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_macro_no_compatibility_contract.py -q` -> 13 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check` -> pass.
- `git diff --check` -> pass.

## 2026-06-17 Continuation — Frontend Module Read Summary Status Fallback Hard Cut

Red tests:

- `cd web && npm run test -- tests/unit/features/macro/model/macroModulePresentation.test.ts --run` failed because `macroReadSummary(...)` still returned `部分可用` from snapshot status when `module_read` had no display summary fields.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts --run -t "missing module-read summaries"` failed because `buildMacroWorkbenchBrief(...)` still carried that status-derived copy as `summary`.
- `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx --run -t "does not use snapshot status"` failed because the overview brief rendered `部分可用` as the summary body.

Implementation notes:

- `macroReadSummary(...)` now reads only `module_read.headline`, `module_read.summary`, and `module_read.regime_label`; it returns `null` when none of those fields has display text.
- `MacroWorkbenchBrief.summary` is nullable, preserving absence through the model instead of inventing copy from status metadata.
- Missing module-read summaries remain absent instead of becoming status-derived copy.
- `AssetDailyBrief` accepts a nullable fallback and no longer uses status metadata as judgement copy.

Green tests and checks:

- `cd web && npm run test -- tests/unit/features/macro/model/macroModulePresentation.test.ts --run` -> 7 passed.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts --run -t "missing module-read summaries"` -> 1 passed, 20 skipped.
- `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx --run -t "does not use snapshot status"` -> 1 passed, 18 skipped.
- `cd web && npm run test -- tests/unit/features/macro/model/macroModulePresentation.test.ts tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run` -> 3 files passed, 47 tests passed.
- `cd web && npm run typecheck` -> pass.

Final checks:

- `cd web && npx prettier --write src/features/macro/model/macroModulePresentation.ts src/features/macro/model/macroWorkbenchModel.ts src/features/macro/ui/workbench/MacroInsightBrief.tsx src/features/macro/ui/assets/AssetDailyBrief.tsx tests/unit/features/macro/model/macroModulePresentation.test.ts tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx` -> unchanged.
- `cd web && npm run test -- tests/unit/features/macro/model/macroModulePresentation.test.ts tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run` -> 3 files passed, 47 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run format:check` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture harness 13 files passed, 73 tests passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_macro_no_compatibility_contract.py -q` -> 13 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check` -> pass.
- `git diff --check` -> pass.
- `rg -n "snapshot\\.status|snapshot\\.status_label|\\"暂无\\"|部分可用" web/src/features/macro/model/macroModulePresentation.ts web/src/features/macro/model/macroWorkbenchModel.ts web/src/features/macro/ui/workbench/MacroInsightBrief.tsx web/src/features/macro/ui/assets/AssetDailyBrief.tsx web/tests/unit/features/macro/model/macroModulePresentation.test.ts web/tests/unit/features/macro/model/macroWorkbenchModel.test.ts web/tests/component/features/macro/MacroModulePages.test.tsx` -> status remains only as brief meta; `暂无` remains only in generic scalar filtering/negative assertions, not as summary copy.
- `rg -n "待确认|待接入|未接入|数据缺口：待补齐数据源|待补齐数据源" src/parallax/domains/macro_intel/services web/src/features/macro` -> no matches.

## 2026-06-17 Continuation — Asset Judgement Empty Panel Hard Cut

Red test:

- `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx --run -t "removes the asset judgement panel"` failed because an asset module with `daily_brief: null` and empty `module_read` still rendered a `今日判断` section containing only `缺少今日判断`.

Implementation notes:

- `MacroAssetOverviewPage` now renders the `今日判断` side section only when a backend daily brief or backend module-read summary exists.
- `AssetDailyBrief` returns `null` when neither a daily-brief headline nor a fallback summary is present, and no longer manufactures `缺少今日判断`.

Green tests and checks:

- `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx --run -t "removes the asset judgement panel"` -> 1 passed, 19 skipped.
- `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx --run -t "asset landing page|pending placeholders when asset snapshot"` -> 2 passed, 18 skipped.
- `cd web && npm run typecheck` -> pass.

Final checks:

- `cd web && npx prettier --write src/features/macro/ui/pages/MacroAssetOverviewPage.tsx src/features/macro/ui/assets/AssetDailyBrief.tsx tests/component/features/macro/MacroModulePages.test.tsx` -> unchanged.
- `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx --run` -> 20 passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run format:check` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture harness 13 files passed, 73 tests passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_macro_no_compatibility_contract.py -q` -> 13 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check` -> pass.
- `git diff --check` -> pass.
- `rg -n "缺少今日判断" web/src/features/macro web/tests/component/features/macro web/tests/unit/features/macro/model` -> no production matches; only the negative component assertion remains.

## 2026-06-17 Continuation — Module Brief Empty Panel Hard Cut

Red tests:

- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts --run -t "missing module-read summaries"` failed because `hasMacroWorkbenchBrief(...)` did not exist.
- `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx --run -t "does not use snapshot status|removes the leaf module brief"` failed because overview and leaf pages still rendered `宏观简报` / `模块简报` panels containing only `缺少模块解读`.

Implementation notes:

- Added `hasMacroWorkbenchBrief(...)`, which treats only `summary` and brief rows as real panel content.
- `MacroOverviewModulePage` and `MacroLeafModulePage` now render `MacroInsightBrief` only when `hasMacroWorkbenchBrief(...)` is true.
- `MacroInsightBrief` returns `null` defensively when called with an empty brief model, and no longer manufactures `缺少模块解读`.

Green tests and checks:

- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts --run -t "missing module-read summaries"` -> 1 passed, 20 skipped.
- `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx --run -t "does not use snapshot status|removes the leaf module brief"` -> 2 passed, 19 skipped.
- `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx --run` -> 21 passed.
- `cd web && npm run typecheck` -> pass.

Final checks:

- `cd web && npx prettier --write src/features/macro/model/macroWorkbenchModel.ts src/features/macro/ui/pages/MacroOverviewModulePage.tsx src/features/macro/ui/pages/MacroLeafModulePage.tsx src/features/macro/ui/workbench/MacroInsightBrief.tsx tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx` -> formatted `MacroInsightBrief.tsx`, other touched files unchanged.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run` -> 2 files passed, 42 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run format:check` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture harness 13 files passed, 73 tests passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_macro_no_compatibility_contract.py -q` -> 13 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check` -> pass.
- `git diff --check` -> pass.
- `rg -n "缺少模块解读|缺少今日判断" web/src/features/macro web/tests/component/features/macro web/tests/unit/features/macro/model` -> no production matches; only negative component assertions remain.

## 2026-06-17 Continuation — Rates Corridor Missing Indicator Copy Hard Cut

Red test:

- `cd web && npm run test -- tests/component/features/macro/MacroRatesWorkbench.test.tsx --run -t "renders the fed funds corridor band and EFFR line"` failed because the rates corridor chart still rendered `待补齐：SOFR 30D` and did not render `缺少指标：SOFR 30D`.

Implementation notes:

- `RatesCorridorChart` now renders `缺少指标：{missingLabels}` for missing corridor series.
- The missing indicator list remains visible; this deletes future-backlog wording rather than hiding the data-health gap.

Green tests and checks:

- `cd web && npm run test -- tests/component/features/macro/MacroRatesWorkbench.test.tsx --run -t "renders the fed funds corridor band and EFFR line"` -> 1 passed, 11 skipped.
- `cd web && npm run test -- tests/component/features/macro/MacroRatesWorkbench.test.tsx --run` -> 12 passed.
- `cd web && npm run test -- tests/unit/features/macro/model/macroRatesChartModel.test.ts tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts --run` -> 2 files passed, 9 tests passed.
- `rg -n "待补齐|待接入|未接入|待确认" web/src/features/macro src/parallax/domains/macro_intel/services` -> no matches.

Final checks:

- `cd web && npx prettier --write src/features/macro/ui/rates/RatesCorridorChart.tsx tests/component/features/macro/MacroRatesWorkbench.test.tsx` -> files unchanged.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run format:check` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture harness 13 files passed, 73 tests passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_macro_no_compatibility_contract.py -q` -> 13 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check` -> pass.
- `git diff --check` -> pass.

## 2026-06-17 Continuation — Macro Fixture Pending Confirmation Copy Hard Cut

Red test:

- `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx --run -t "renders inflation diagnostics"` failed because the inflation fixture rendered `PCE 尚待确认` in `驱动与反证` and did not render the desired `PCE 发布窗口`.

Implementation notes:

- `macroInflationModuleFixture()` now labels the PCE contradiction as `PCE 发布窗口`.
- The detail text describes the next BEA PCE release as a validation event for whether CPI reacceleration has spread to PCE.
- This touches mock/test data only; no runtime fallback or hidden fixture branch was added.

Green tests and checks:

- `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx --run -t "renders inflation diagnostics"` -> 1 passed, 17 skipped.
- `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx --run` -> 18 passed.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/unit/features/macro/model/macroModulePresentation.test.ts --run` -> 2 files passed, 26 tests passed.
- `rg -n "尚待确认|待确认|待补齐|待接入|未接入" web/tests/fixtures/macroFixture.ts web/tests/e2e/support/mockApi.ts web/src/features/macro src/parallax/domains/macro_intel/services` -> no matches.

Final checks:

- `cd web && npx prettier --write tests/component/features/macro/MacroModulePages.test.tsx tests/fixtures/macroFixture.ts` -> formatted touched fixture/test files.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run format:check` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture harness 13 files passed, 73 tests passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_macro_no_compatibility_contract.py -q` -> 13 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check` -> pass.
- `git diff --check` -> pass.

## 2026-06-17 Continuation — Frontend Unlabeled Gap Sentinel Hard Cut

Red tests:

- `cd web && npm run test -- tests/unit/features/macro/model/macroPageViewModel.test.ts --run` failed because `gapLabel({})` still returned `未标注数据缺口`.
- `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx --run` failed because the overview data-health fixture still rendered `部分全局历史待回填`.

Implementation notes:

- `gapLabel(...)` now returns `null` for unlabeled/unknown gap payloads instead of manufacturing the `未标注数据缺口` sentinel.
- `buildMacroDataHealthBuckets(...)` drops unknown gap payloads directly by checking for a missing label.
- The overview fixture global-history gap now renders as `全局历史样本不足` with `需要补充全局宏观历史后再生成总览投影。`.

Green tests and checks:

- `cd web && npm run test -- tests/unit/features/macro/model/macroPageViewModel.test.ts --run` -> 9 passed.
- `cd web && npm run test -- tests/unit/features/macro/model/macroModulePresentation.test.ts --run` -> 6 passed.
- `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx --run` -> 18 passed.
- `cd web && npm run test -- tests/unit/features/macro/model/macroPageViewModel.test.ts tests/unit/features/macro/model/macroModulePresentation.test.ts --run` -> 2 files passed, 15 tests passed.
- `rg -n "待回填|待补齐|待接入|待确认|尚待确认|未标注数据缺口" web/src/features/macro web/tests/fixtures web/tests/component/features/macro web/tests/unit/features/macro src/parallax/domains/macro_intel tests/unit/domains/macro_intel tests/architecture/test_macro_no_compatibility_contract.py` -> no production or fixture matches; only negative test assertions remain.
- `cd web && npm run typecheck` -> pass.

Final checks:

- `cd web && npx prettier --write src/features/macro/model/macroPageViewModel.ts src/features/macro/model/macroModulePresentation.ts tests/unit/features/macro/model/macroPageViewModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx tests/fixtures/macroFixture.ts` -> unchanged.
- `cd web && npm run test -- tests/unit/features/macro/model/macroPageViewModel.test.ts tests/unit/features/macro/model/macroModulePresentation.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run` -> 3 files passed, 33 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run format:check` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture harness 13 files passed, 73 tests passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_macro_no_compatibility_contract.py -q` -> 13 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check` -> pass.
- `git diff --check` -> pass.

## 2026-06-17 Continuation — Decision Console Empty Section Hard Cut

Red test:

- `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx --run` failed because an overview page with confirmations/contradictions but no decision-console read payload still rendered empty `3 个最重要变化` with `暂无关键变化`.

Implementation notes:

- `MacroDecisionConsolePanel` now returns `null` for empty top-change, paired evidence, trade-map, scenario-case, and data-credibility subsections.
- The retained `今日决策台` still renders sections with real backend content, such as `确认 / 背离`; empty subsections are deleted from the DOM rather than hidden.

Green tests and checks:

- `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx --run` -> 21 passed.
- `cd web && npx prettier --write src/features/macro/ui/workbench/MacroDecisionConsolePanel.tsx tests/component/features/macro/MacroModulePages.test.tsx ../docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md ../docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md` -> formatted touched decision-console and SDD files; test file unchanged.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run` -> 2 files passed, 42 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run format:check` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture harness 13 files passed, 73 tests passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_macro_no_compatibility_contract.py -q` -> 13 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check` -> pass.
- `git diff --check` -> pass.
- `rg -n "暂无关键变化|暂无确认或背离|暂无交易映射|暂无情景计划|暂无阻断缺口" web/src/features/macro web/tests/component/features/macro web/tests/unit/features/macro/model docs/sdd/features/active/2026-06-16-macro-decision-console` -> no production matches; only SDD notes and negative component assertions remain.

## 2026-06-17 Continuation — Driver Board Empty Panel Hard Cut

Red tests:

- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run` failed because `hasMacroWorkbenchDrivers(...)` did not exist.
- The same run failed because a leaf page with empty `module_evidence` and empty `transmission` still rendered `驱动与反证`, including `传导路径 / 暂无` and `暂无可用证据`.

Implementation notes:

- Added `hasMacroWorkbenchDrivers(...)`, which requires at least one evidence item or transmission node.
- `MacroOverviewModulePage` and `MacroLeafModulePage` now mount `MacroDriverBoard` only when real driver content exists.
- `MacroDriverBoard` defensively returns `null` when both sides are empty and renders only the populated child section when one side is absent.

Green tests and checks:

- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run` -> 2 files passed, 44 tests passed.
- `cd web && npx prettier --write src/features/macro/model/macroWorkbenchModel.ts src/features/macro/ui/pages/MacroOverviewModulePage.tsx src/features/macro/ui/pages/MacroLeafModulePage.tsx src/features/macro/ui/workbench/MacroDriverBoard.tsx tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx ../docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md ../docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md` -> all touched files unchanged.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run format:check` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture harness 13 files passed, 73 tests passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_macro_no_compatibility_contract.py -q` -> 13 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check` -> pass.
- `git diff --check` -> pass.
- `rg -n "暂无可用证据|传导路径\\W*</span>\\s*<b>\\s*暂无|缺少模块解读|缺少今日判断" web/src/features/macro web/tests/component/features/macro web/tests/unit/features/macro/model docs/sdd/features/active/2026-06-16-macro-decision-console` -> no production matches; only SDD notes and negative component assertions remain.

## 2026-06-17 Continuation — Data Gap Empty Detail Hard Cut

Red tests:

- `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx --run` failed because a leaf module with zero data gaps still rendered `缺口明细` and `暂无数据缺口`.
- The same run failed because the asset overview diagnostics rail still rendered `暂无数据缺口` when `gapCount` was zero.

Implementation notes:

- `MacroDiagnosticsPanel` filters to gap buckets with real items or nonzero reference counts and renders `缺口明细` only when that filtered list is nonempty.
- `AssetDiagnosticsBoard` applies the same filtered-bucket rule and returns `null` for the gap detail section when `gapCount` is zero.
- The retained diagnostics summaries still show status, source count, and numeric gap count.

Green tests and checks:

- `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx --run` -> 24 passed.
- `cd web && npx prettier --write src/features/macro/ui/workbench/MacroDiagnosticsPanel.tsx src/features/macro/ui/assets/AssetDiagnosticsBoard.tsx tests/component/features/macro/MacroModulePages.test.tsx ../docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md ../docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md` -> all touched files unchanged.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run` -> 2 files passed, 46 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run format:check` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture harness 13 files passed, 73 tests passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_macro_no_compatibility_contract.py -q` -> 13 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check` -> pass.
- `git diff --check` -> pass.
- `rg -n "暂无数据缺口|缺口明细|macro-workbench-health-bucket|macro-assets-health-empty" web/src/features/macro web/tests/component/features/macro docs/sdd/features/active/2026-06-16-macro-decision-console` -> no production empty-state text matches; remaining production hits are populated gap-detail markup/CSS, plus SDD notes and negative assertions.

## 2026-06-17 Continuation — Source Detail Empty State Hard Cut

Red tests:

- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run` failed because missing provenance still produced `暂无来源`.
- The same run failed because leaf and asset diagnostics with `provenance.rows: []` still rendered source drawers containing `暂无数据源元信息`.

Implementation notes:

- `buildMacroWorkbenchDiagnostics(...)` now formats zero provenance as `0 个来源`.
- `MacroDiagnosticsPanel` renders the source status drawer only when `diagnostics.sourceCount > 0`.
- `AssetDiagnosticsBoard` renders the source drawer only when `summary.sourceCount > 0`.

Green tests and checks:

- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run` -> 2 files passed, 48 tests passed.

## 2026-06-17 Continuation — Rates Empty Fact And Diagnostics Hard Cut

Red tests:

- `cd web && npm run test -- tests/component/features/macro/MacroRatesWorkbench.test.tsx --run` failed because a rates module with no facts still rendered `关键事实` containing `暂无关键事实`.
- The same run failed because a rates fact missing source/date/status still rendered `暂无来源`, `暂无日期`, and `暂无状态`.
- The same run failed because rates diagnostics with no gap payloads and no provenance rows still rendered empty buckets, `来源状态`, and `暂无数据源元信息`.

Implementation notes:

- `RatesFactStrip` now returns `null` for empty fact arrays and renders only present fact metadata fields.
- `RatesFact.observedAtLabel` is nullable, and `buildRatesFact(...)` no longer manufactures `暂无日期`.
- `RatesDiagnosticsPanel` filters empty buckets and renders source diagnostics only when provenance rows exist.

Green tests and checks:

- `cd web && npm run test -- tests/component/features/macro/MacroRatesWorkbench.test.tsx --run` -> 15 passed.

## 2026-06-17 Continuation — Rates Decision Support Empty Group Hard Cut

Red tests:

- `cd web && npm run test -- tests/component/features/macro/MacroRatesWorkbench.test.tsx --run` failed because a rates module with empty confirmations, contradictions, watch triggers, and invalidations still rendered `决策支持` with four empty groups and `暂无`.
- The same run failed because a rates evidence item with a label but no description rendered the detail as `暂无`.

Implementation notes:

- `RatesDecisionSupport` now filters to groups with items and returns `null` when the item count is zero.
- `RatesDecisionGroup` item detail is nullable, and `decisionGroups(...)` no longer manufactures a `暂无` detail.
- Decision support item details render only when present.

Green tests and checks:

- `cd web && npm run test -- tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts tests/component/features/macro/MacroRatesWorkbench.test.tsx --run` -> 2 files passed, 24 tests passed.
- `cd web && npm run typecheck` -> pass.

## 2026-06-17 Continuation — Missing As-Of Date Hard Cut

Red tests:

- `cd web && npm run test -- tests/unit/features/macro/model/macroPageViewModel.test.ts --run` failed because `macroAsOfLabel(...)` still returned `暂无日期` and freshness alerts included `暂无日期；...`.
- `cd web && npm run test -- tests/component/features/macro/MacroRatesWorkbench.test.tsx --run` failed because the rates read panel still rendered `截至 / 暂无日期`.

Implementation notes:

- `macroAsOfLabel(...)` and its date formatter now return `null` when no snapshot date exists.
- Freshness alert details use an as-of prefix only when a real label exists.
- Macro route headers filter out missing `截至` status items, and `RatesMarketRead` omits the as-of state row and meta suffix when absent.

Green tests and checks:

- `cd web && npm run test -- tests/unit/features/macro/model/macroPageViewModel.test.ts tests/component/features/macro/MacroRatesWorkbench.test.tsx --run` -> 2 files passed, 29 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npx prettier --write src/features/macro/model/macroPageViewModel.ts src/features/macro/MacroWorkbenchRoute.tsx src/features/macro/model/macroRatesWorkbenchModel.ts src/features/macro/ui/rates/RatesMarketRead.tsx tests/unit/features/macro/model/macroPageViewModel.test.ts tests/component/features/macro/MacroRatesWorkbench.test.tsx ../docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md ../docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md` -> formatted `MacroWorkbenchRoute.tsx`; other touched files unchanged.
- `cd web && npm run test -- tests/unit/features/macro/model/macroPageViewModel.test.ts tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx tests/component/features/macro/MacroRatesWorkbench.test.tsx --run` -> 5 files passed, 84 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run format:check` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture harness 13 files passed, 73 tests passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_macro_no_compatibility_contract.py -q` -> 13 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check` -> pass.
- `git diff --check` -> pass.
- `rg -n "暂无关键事实|暂无来源|暂无日期|暂无状态|暂无数据源元信息|>暂无<|暂无</" web/src/features/macro web/tests/component/features/macro web/tests/unit/features/macro/model docs/sdd/features/active/2026-06-16-macro-decision-console` -> no product-surface matches for the cleaned paths at that point; the remaining standalone `MacroSourceTable` primitive empty state was removed in the later source-table primitive hard cut.

## 2026-06-17 Continuation — Source Gap Priority Tightening

External source refresh:

- Re-opened `https://timsun.net/`; the benchmark still presents a first-screen macro decision console with Trade Map, top changes, liquidity pressure, 24h/72h catalysts, data credibility, structured analysis, event flow, and watchlist triggers.
- Re-opened OFR STFM API docs; it is public, tokenless, JSON-based, versioned under `https://data.financialresearch.gov/v1`, and exposes metadata plus time-series endpoints.
- Re-opened Cboe CFE historical data; the futures market-statistics surface exposes historical-data/archive and settlement/open-interest style entry points that can support the next volatility-depth slice.
- Re-opened BLS developer docs and BEA API docs; both remain official public entry points for published economic data/metadata, while consensus surprise still needs a separate expectations source.

Implementation notes:

- Added `First-Principles Source Priority` to `docs/references/MACRO_TIMSUN_SOURCE_GAP_MAP.md`.
- Ranked next public-source work as OFR STFM, BLS/BEA actual/revision, Cboe CFE futures history, internal Trade Map judgement history, and Fed text delta scoring.
- Explicitly kept CME FedWatch, OPRA/GEX, TRACE/CDS/CDX, broad cross-currency basis, and consensus surprise license/model-gated with no runtime route or placeholder surface.

Green tests and checks:

- `cd web && npx prettier --write ../docs/references/MACRO_TIMSUN_SOURCE_GAP_MAP.md ../docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md ../docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md` -> formatted gap map; SDD files unchanged.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check` -> pass.
- `rg -n 'fallback now says \`暂无来源\`|falls back to \`暂无来源\`|diagnostics fallback now says \`暂无来源\`' docs/sdd/features/active/2026-06-16-macro-decision-console docs/references/MACRO_TIMSUN_SOURCE_GAP_MAP.md` -> no matches.
- `git diff --check` -> pass.

## 2026-06-17 Continuation — Runtime No-Resurrection Architecture Guard

Implementation notes:

- Added `HARD_DELETED_MACRO_MODULE_IDS` to
  `tests/architecture/test_macro_no_compatibility_contract.py` and scan runtime
  macro/frontend source for deleted `/macro/...` product route paths.
- Added explicit removal checks for `MacroMatrixPage.tsx` and
  `CorrelationRead.tsx`, the old standalone asset-correlation page components.
- Added a runtime placeholder scan for source-backlog product copy, including
  FedWatch, OPRA, TRACE, CDS/CDX, DataShop/LiveVol, auction-tail, when-issued,
  and STFM.
- Kept the retained asset page's correlation data endpoint/query as the only
  allowed `assets/correlation` reference; it is data plumbing, not a restored
  product route or compatibility shell.

Green tests and checks:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_macro_no_compatibility_contract.py -q` -> 16 passed.

## 2026-06-17 Continuation — Source Table Primitive Empty State Hard Cut

Red test:

- `cd web && npm run test -- tests/component/features/macro/MacroDataTable.test.tsx --run` failed because `MacroSourceTable` still rendered `旧数据源空状态` with `暂无数据源元信息` for a legacy source metadata object.

Implementation notes:

- `MacroSourceTable` now returns `null` when `source.rows` does not produce valid rows.
- The primitive still refuses to infer rows from a legacy one-object source metadata payload and still does not expose raw provider/status/run ids.

Green tests and checks:

- `cd web && npm run test -- tests/component/features/macro/MacroDataTable.test.tsx --run` -> 7 passed.
- `cd web && npx prettier --write src/features/macro/ui/tables/MacroSourceTable.tsx tests/component/features/macro/MacroDataTable.test.tsx ../docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md ../docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md` -> all touched files unchanged.
- `rg -n "暂无数据源元信息" web/src/features/macro` -> no production matches.
- `cd web && npm run test -- tests/component/features/macro/MacroDataTable.test.tsx tests/component/features/macro/MacroModulePages.test.tsx tests/component/features/macro/MacroRatesWorkbench.test.tsx --run` -> 3 files passed, 51 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run test:architecture` -> 13 files passed, 73 tests passed.
- `cd web && npm run lint` -> ESLint passed; architecture harness 13 files passed, 73 tests passed.
- `cd web && npm run format:check` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_macro_no_compatibility_contract.py -q` -> 16 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check` -> pass.
- `git diff --check` -> pass.

## 2026-06-17 Continuation — Source Row Placeholder Hard Cut

Red test:

- `cd web && npm run test -- tests/component/features/macro/MacroDataTable.test.tsx --run` failed because `MacroSourceTable` still rendered `暂无` sparse cells, a generic `数据源` row, and an unknown internal provider status for source metadata rows without a real provider label.

Implementation notes:

- `MacroSourceTable` now builds its own evidence table instead of routing source metadata through the generic `MacroDataTable` sparse-cell fallback.
- Source rows now require a real provider label and at least one audit fact; unknown internal provider ids are dropped.
- Optional source columns render only when at least one kept row has a real value, so missing count/score/notes fields no longer become `暂无` product cells.
- The custom source table carries no dead sort payload; once the generic sortable table was removed, row cells kept only their rendered value.

Green tests and checks:

- `cd web && npm run test -- tests/component/features/macro/MacroDataTable.test.tsx --run` -> 8 passed.
- `cd web && npx prettier --write src/features/macro/ui/tables/MacroSourceTable.tsx tests/component/features/macro/MacroDataTable.test.tsx ../docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md ../docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md` -> all touched files unchanged.
- `cd web && npm run test -- tests/unit/features/macro/model/macroAssetOverviewModel.test.ts tests/component/features/macro/MacroDataTable.test.tsx tests/component/features/macro/MacroModulePages.test.tsx tests/component/features/macro/MacroRatesWorkbench.test.tsx --run` -> 4 files passed, 64 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run format:check` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture harness 13 files passed, 73 tests passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_macro_no_compatibility_contract.py -q` -> 16 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py` -> pass.
- `cd web && npm run test:e2e -- tests/e2e/golden-paths/macro-responsive-audit.spec.ts --project=desktop-1366` -> 1 passed; Vite emitted the existing chunk-size warning.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check` -> pass.
- `git diff --check` -> pass.

## 2026-06-17 Continuation — Decision Console Sparse Item Hard Cut

Red test:

- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts --run` failed because sparse confirmation evidence still entered the decision console with a generated placeholder detail.

Implementation notes:

- `decisionItem(...)`, `qualityItem(...)`, `evidenceItem(...)`, and `watchlistRuleItem(...)` now require a real detail after scalar formatting.
- `buildMacroDecisionConsole(...)` therefore drops label-only confirmations, contradictions, top changes, quality blockers, and watchlist rules before the UI receives them.

Green tests and checks:

- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts --run` -> 23 passed.
- `cd web && npx prettier --write src/features/macro/model/macroWorkbenchModel.ts tests/unit/features/macro/model/macroWorkbenchModel.test.ts ../docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md ../docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md` -> formatted `tests/unit/features/macro/model/macroWorkbenchModel.test.ts`; other touched files unchanged.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/unit/features/macro/model/macroModulePresentation.test.ts tests/component/features/macro/MacroModulePages.test.tsx tests/component/features/macro/MacroRatesWorkbench.test.tsx --run` -> 4 files passed, 85 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run format:check` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture harness 13 files passed, 73 tests passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_macro_no_compatibility_contract.py -q` -> 16 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py` -> pass.
- `cd web && npm run test:e2e -- tests/e2e/golden-paths/macro-responsive-audit.spec.ts --project=desktop-1366` -> 1 passed; Vite emitted the existing chunk-size warning.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check` -> pass.
- `git diff --check` -> pass.
- `rg -n "暂无|数据源元信息|provider_not_configured|缺少日期" web/src/features/macro/ui/tables/MacroSourceTable.tsx web/src/features/macro/ui/assets web/src/features/macro/model/macroAssetOverviewModel.ts` -> no source-table product matches; remaining hits are input filters in asset code.
- `cd web && npm run test -- tests/component/features/macro/MacroDataTable.test.tsx --run` -> 8 passed after deleting the unused source-row sort payload.
- `cd web && npm run typecheck` -> pass after deleting the unused source-row sort payload.

## 2026-06-17 Continuation — Generic Metric And Evidence Placeholder Hard Cut

Red test:

- `cd web && npm run test -- tests/unit/features/macro/model/macroModulePresentation.test.ts --run` failed because `buildMacroMetrics(...)` still emitted an empty VIX tile with a formatted placeholder value, and generic evidence formatting still allowed sparse evidence rows to become product items.

Implementation notes:

- `buildMacroMetrics(...)` now emits a metric only when the tile has a real label or short label and a real formatted value.
- Generic evidence groups now require both label and detail before an item enters the presentation model.
- The no-compatibility test fixture was updated to use a real v3 evidence detail instead of relying on the old label-only evidence behavior.

Green tests and checks:

- `cd web && npm run test -- tests/unit/features/macro/model/macroModulePresentation.test.ts --run` -> 8 passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run format:check` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_macro_no_compatibility_contract.py -q` -> 16 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture harness 13 files passed, 73 tests passed.
- `cd web && npm run test:e2e -- tests/e2e/golden-paths/macro-responsive-audit.spec.ts --project=desktop-1366` -> 1 passed; Vite emitted the existing chunk-size warning.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check` -> pass.
- `git diff --check` -> pass.

## 2026-06-17 Continuation — Backend Unnamed Indicator Hard Cut

Red test:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_macro_no_compatibility_contract.py -q` failed because macro runtime source still contained `未命名指标` in `macro_gap_payloads.py`, `macro_series_view.py`, and `macro_module_views.py`.

Implementation notes:

- Added a macro architecture guard that rejects runtime source containing the anonymous indicator placeholder.
- `macro_series_view` now requires label metadata for supported series concepts.
- `macro_module_views` now requires feature or concept metadata for public tile/table labels.
- `macro_gap_payloads` maps unmapped `missing:*` codes to `数据质量缺口：{public_code}` instead of manufacturing an indicator name.

Green tests and checks:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_series_view.py tests/unit/domains/macro_intel/test_macro_module_views.py -q` -> 107 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_macro_no_compatibility_contract.py -q` -> 17 passed.
- `rg -n "未命名指标" src/parallax/domains/macro_intel src/parallax/app/surfaces/api/routes_macro.py src/parallax/app/surfaces/cli/commands/macro.py web/src/features/macro web/src/routes/macro.route.tsx web/src/features/cockpit/ui/appNavigation.ts tests/unit/domains/macro_intel tests/architecture/test_macro_no_compatibility_contract.py` -> no runtime source matches; remaining hits are the architecture token and unit-test negative assertion.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format src/parallax/domains/macro_intel/services/macro_gap_payloads.py src/parallax/domains/macro_intel/services/macro_series_view.py src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_series_view.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/architecture/test_macro_no_compatibility_contract.py` -> 3 files reformatted, 3 unchanged.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/macro_intel/services/macro_gap_payloads.py src/parallax/domains/macro_intel/services/macro_series_view.py src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_series_view.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/architecture/test_macro_no_compatibility_contract.py` -> 6 files already formatted.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/macro_intel/services/macro_gap_payloads.py src/parallax/domains/macro_intel/services/macro_series_view.py src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_series_view.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/architecture/test_macro_no_compatibility_contract.py` -> all checks passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_series_view.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/domains/macro_intel/test_macro_scenario_engine.py tests/unit/test_api_macro_contract.py tests/unit/test_cli_macro_commands.py tests/architecture/test_macro_no_compatibility_contract.py -q` -> 204 passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run format:check` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture harness 13 files passed, 73 tests passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check` -> pass.
- `git diff --check` -> pass.

## 2026-06-17 Continuation — Backend Empty Chart Factory Hard Cut

Red test:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_macro_no_compatibility_contract.py -q` failed because `macro_module_views.py` still contained `_empty_chart`.

Implementation notes:

- Added a catalog invariant that all retained macro modules have a primary chart spec.
- Added a macro architecture guard that rejects `_empty_chart` in runtime source.
- `build_macro_module_view(...)` and the missing-snapshot path now require `config.chart_specs[0]` and no longer fabricate an `id: None` chart shell.

Green tests and checks:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_catalog.py -q` -> 35 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/domains/macro_intel/test_macro_module_views.py -q` -> 135 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_macro_no_compatibility_contract.py -q` -> 18 passed.
- `rg -n "_empty_chart" src/parallax/domains/macro_intel tests/architecture/test_macro_no_compatibility_contract.py tests/unit/domains/macro_intel/test_macro_module_catalog.py` -> no runtime source matches; remaining hits are the architecture token and test name.
- `cd web && npx prettier --write ../docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md ../docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md` -> all touched SDD files unchanged.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/architecture/test_macro_no_compatibility_contract.py` -> 3 files unchanged.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/architecture/test_macro_no_compatibility_contract.py` -> all checks passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_series_view.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/domains/macro_intel/test_macro_scenario_engine.py tests/unit/test_api_macro_contract.py tests/unit/test_cli_macro_commands.py tests/architecture/test_macro_no_compatibility_contract.py -q` -> 240 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py` -> pass.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run format:check` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture harness 13 files passed, 73 tests passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check` -> pass.
- `git diff --check` -> pass.
- `rg -n "未命名指标|_empty_chart|emptyTable\\(|emptyChart\\(|_supporting_table" src/parallax/domains/macro_intel src/parallax/app/surfaces/api/routes_macro.py src/parallax/app/surfaces/cli/commands/macro.py web/src/features/macro web/src/routes/macro.route.tsx web/src/features/cockpit/ui/appNavigation.ts tests/architecture/test_macro_no_compatibility_contract.py tests/unit/domains/macro_intel web/tests/unit/features/macro/model web/tests/component/features/macro` -> no runtime source matches; remaining hits are architecture tokens and negative assertions.

## 2026-06-17 Continuation — Chart Series Placeholder Hard Cut

Red test:

- `cd web && npm run test -- tests/unit/features/macro/model/macroChartModel.test.ts --run` failed because an unlabeled `asset:spx` time-series still entered the chart model as `未命名指标`.

Implementation notes:

- `buildMacroTimeSeriesModel(...)` now drops canonical series that lack a real display label instead of emitting `未命名指标`.
- `buildMacroHeatmapMatrix(...)` now drops unlabeled canonical rows before building matrix columns and cells.
- Known yield-curve tenor labels such as `10Y` remain because they are deterministic semantic labels from Treasury concepts, not generic placeholder copy.

Green tests and checks:

- `cd web && npm run test -- tests/unit/features/macro/model/macroChartModel.test.ts --run` -> 7 passed.
- `cd web && npx prettier --write src/features/macro/model/macroChartModel.ts tests/unit/features/macro/model/macroChartModel.test.ts ../docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md ../docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md` -> all touched files unchanged.
- `cd web && npm run test -- tests/unit/features/macro/model/macroChartModel.test.ts tests/unit/features/macro/model/macroCorrelationModel.test.ts tests/component/features/macro/MacroCharts.test.tsx tests/component/features/macro/MacroModulePages.test.tsx tests/component/features/macro/MacroRatesWorkbench.test.tsx --run` -> 5 files passed, 72 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run format:check` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture harness 13 files passed, 73 tests passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_macro_no_compatibility_contract.py -q` -> 16 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py` -> pass.
- `cd web && npm run test:e2e -- tests/e2e/golden-paths/macro-responsive-audit.spec.ts --project=desktop-1366` -> 1 passed; Vite emitted the existing chunk-size warning.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check` -> pass.
- `git diff --check` -> pass.

## 2026-06-17 Continuation — Generic Table Placeholder Hard Cut

Red tests:

- `cd web && npm run test -- tests/unit/features/macro/model/macroTableColumns.test.ts tests/component/features/macro/MacroDataTable.test.tsx --run` failed because `formatMacroTableValue(...)` still returned `暂无` for null/arbitrary values, `buildMacroTableModel(...)` still kept empty rows/columns, and `MacroDataTable` still rendered missing cells as `暂无`.

Implementation notes:

- `formatMacroTableValue(...)` now returns `null` for missing, empty, arbitrary-object, and literal `暂无` inputs.
- `buildMacroTableModel(...)` now drops empty cells, rows with no displayable cells, and columns with no displayable cells.
- `MacroDataTable` now renders absent cells as absent content, while explicit backend strings such as `缺失` continue to display.

Green tests and checks:

- `cd web && npm run test -- tests/unit/features/macro/model/macroTableColumns.test.ts tests/component/features/macro/MacroDataTable.test.tsx --run` -> 2 files passed, 15 tests passed.
- `cd web && npx prettier --write src/features/macro/model/macroTableColumns.ts src/features/macro/ui/tables/MacroDataTable.tsx tests/unit/features/macro/model/macroTableColumns.test.ts tests/component/features/macro/MacroDataTable.test.tsx ../docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md ../docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md` -> formatted `src/features/macro/model/macroTableColumns.ts`; other touched files unchanged.
- `cd web && npm run test -- tests/unit/features/macro/model/macroTableColumns.test.ts tests/unit/features/macro/model/macroAssetOverviewModel.test.ts tests/unit/features/macro/model/macroChartModel.test.ts tests/component/features/macro/MacroDataTable.test.tsx tests/component/features/macro/MacroModulePages.test.tsx tests/component/features/macro/MacroRatesWorkbench.test.tsx --run` -> 6 files passed, 78 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run format:check` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture harness 13 files passed, 73 tests passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_macro_no_compatibility_contract.py -q` -> 16 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py` -> pass.
- `cd web && npm run test:e2e -- tests/e2e/golden-paths/macro-responsive-audit.spec.ts --project=desktop-1366` -> 1 passed; Vite emitted the existing chunk-size warning.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check` -> pass.
- `git diff --check` -> pass.

## 2026-06-17 Continuation — Nullable Scalar Formatter Hard Cut

Red tests:

- `cd web && npm run test -- tests/unit/features/macro/model/macroPageViewModel.test.ts tests/unit/features/macro/model/macroWorkbenchModel.test.ts --run` failed because `formatMacroScalar(...)` still returned `暂无` for null input and `buildMacroWorkbenchBrief(...)` still emitted `暂无` module-read rows for arbitrary objects.
- `cd web && npm run test -- tests/component/features/macro/MacroDriverBoard.test.tsx --run` failed because a transmission node with a label but placeholder value still rendered in the flow list.
- `cd web && npm run test -- tests/component/features/macro/MacroMarketBoard.test.tsx --run` failed because an empty table source note still rendered an empty `.macro-table-source-note` paragraph.

Implementation notes:

- `formatMacroScalar(...)` now returns `string | null`, with `null` for missing, empty, arbitrary-object, empty-array, and literal `暂无` values.
- Macro model callers now filter nullable scalar output before emitting brief rows, structured-analysis fields, liquidity pressure details, event-flow rows, future catalysts, and rates facts.
- `MacroDriverBoard` now builds transmission rows only when both label and value format to real text.
- `MacroMarketBoard` now renders table source notes only when the formatted note is real text.

Green tests and checks:

- `cd web && npm run test -- tests/unit/features/macro/model/macroPageViewModel.test.ts tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroDriverBoard.test.tsx --run` -> 3 files passed, 37 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run test -- tests/unit/features/macro/model/macroPageViewModel.test.ts tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts tests/component/features/macro/MacroDriverBoard.test.tsx tests/component/features/macro/MacroMarketBoard.test.tsx --run` -> 5 files passed, 46 tests passed.
- `cd web && npx prettier --write src/features/macro/model/macroPageViewModel.ts src/features/macro/model/macroModulePresentation.ts src/features/macro/model/macroWorkbenchModel.ts src/features/macro/model/macroRatesWorkbenchModel.ts src/features/macro/ui/workbench/MacroDriverBoard.tsx src/features/macro/ui/pages/MacroMarketBoard.tsx tests/unit/features/macro/model/macroPageViewModel.test.ts tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts tests/component/features/macro/MacroDriverBoard.test.tsx tests/component/features/macro/MacroMarketBoard.test.tsx ../docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md ../docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md` -> formatted `src/features/macro/model/macroRatesWorkbenchModel.ts`; other touched files unchanged.
- `cd web && npm run test -- tests/unit/features/macro/model/macroPageViewModel.test.ts tests/unit/features/macro/model/macroModulePresentation.test.ts tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts tests/component/features/macro/MacroDriverBoard.test.tsx tests/component/features/macro/MacroMarketBoard.test.tsx tests/component/features/macro/MacroModulePages.test.tsx tests/component/features/macro/MacroRatesWorkbench.test.tsx --run` -> 8 files passed, 108 tests passed.
- `cd web && npm run typecheck` -> pass after formatting.
- `cd web && npm run format:check` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture harness 13 files passed, 73 tests passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_macro_no_compatibility_contract.py -q` -> 16 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py` -> pass.
- `cd web && npm run test:e2e -- tests/e2e/golden-paths/macro-responsive-audit.spec.ts --project=desktop-1366` -> 1 passed; Vite emitted the existing chunk-size warning.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check` -> pass.
- `git diff --check` -> pass after re-running once the Playwright-updated `web/test-results/.last-run.json` was present on disk.

## 2026-06-17 Continuation — Market Board Empty Chart Hard Cut

Red tests:

- `cd web && npm run test -- tests/component/features/macro/MacroMarketBoard.test.tsx --run` failed because a table-backed market board with an empty chart still rendered `暂无可绘制序列`.
- The same test file then failed on an unlabeled raw `asset:spx` chart series because the page-level board still mounted chart chrome after the chart model filtered the series out.

Implementation notes:

- `MacroMarketBoard` now uses `hasRenderablePrimaryChart(...)` to decide whether a primary visual is real product evidence.
- The helper checks yield-curve points, normalized-return series, or generic time-series model output instead of raw `chart.series.length`.
- A panel with tables but no drawable chart keeps the tables and omits the empty chart region; chart primitives retain direct-use empty states outside this product surface.

Green tests and checks:

- `cd web && npm run test -- tests/component/features/macro/MacroMarketBoard.test.tsx --run` -> 2 passed.
- `cd web && npm run test -- tests/component/features/macro/MacroMarketBoard.test.tsx tests/component/features/macro/MacroModulePages.test.tsx tests/component/features/macro/MacroCharts.test.tsx tests/component/features/macro/MacroRatesWorkbench.test.tsx tests/unit/features/macro/model/macroChartModel.test.ts --run` -> 5 files passed, 72 tests passed.
- `cd web && npm run typecheck` -> pass.

## 2026-06-17 Continuation — Rates Corridor Empty Primary Visual Hard Cut

Red test:

- `cd web && npm run test -- tests/component/features/macro/MacroRatesWorkbench.test.tsx --run` failed because a `rates/fed-funds` module with one unrecognized raw chart series still mounted `利率主图` and showed a chart loading shell.
- `cd web && npm run test -- tests/component/features/macro/RatesCorridorChart.test.tsx --run` failed because an empty corridor model still rendered a `<figure>` with `暂无可绘制走廊数据`.

Implementation notes:

- `RatesPrimaryVisual` now checks whether a Fed funds primary chart contains at least one recognized corridor concept before allowing the series query to fetch and before mounting the panel.
- Once series loading completes, the Fed funds visual also requires a drawable `RatesCorridorModel` with at least one lower/upper/line series.
- Unknown proxy series and empty corridor models therefore delete the primary visual rather than surfacing loading chrome or `暂无可绘制走廊数据`.
- `RatesCorridorChart` now returns `null` when the geometry has no drawable data, so the component itself no longer preserves an empty chart compatibility branch.

Green tests and checks:

- `cd web && npm run test -- tests/component/features/macro/MacroRatesWorkbench.test.tsx --run` -> 21 passed.
- `cd web && npm run test -- tests/component/features/macro/RatesCorridorChart.test.tsx tests/component/features/macro/MacroRatesWorkbench.test.tsx --run` -> 2 files passed, 22 tests passed.
- `cd web && npx prettier --write src/features/macro/ui/rates/RatesPrimaryVisual.tsx src/features/macro/ui/rates/RatesCorridorChart.tsx tests/component/features/macro/RatesCorridorChart.test.tsx tests/component/features/macro/MacroRatesWorkbench.test.tsx ../docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md ../docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md` -> formatted `src/features/macro/ui/rates/RatesCorridorChart.tsx`; other files unchanged.
- `cd web && npm run test -- tests/component/features/macro/RatesCorridorChart.test.tsx tests/component/features/macro/MacroRatesWorkbench.test.tsx tests/component/features/macro/MacroModulePages.test.tsx tests/component/features/macro/MacroMarketBoard.test.tsx tests/component/features/macro/MacroCharts.test.tsx tests/unit/features/macro/model/macroRatesChartModel.test.ts tests/unit/features/macro/model/macroChartModel.test.ts --run` -> 7 files passed, 76 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run format:check` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_macro_no_compatibility_contract.py -q` -> 16 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture harness 13 files passed, 73 tests passed.
- `cd web && npm run test:e2e -- tests/e2e/golden-paths/macro-responsive-audit.spec.ts --project=desktop-1366` -> 1 passed; Vite emitted the existing chunk-size warning.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check` -> pass.
- `git diff --check` -> pass.
- `rg -n "暂无可绘制走廊数据|暂无可绘制序列|暂无收益率曲线数据|暂无相关性矩阵数据" web/src/features/macro/ui/pages web/src/features/macro/ui/rates web/src/features/macro/ui/assets web/src/features/macro/ui/workbench` -> no matches.

## 2026-06-17 Continuation — Generic Table Empty State Hard Cut

Red test:

- `cd web && npm run test -- tests/component/features/macro/MacroDataTable.test.tsx --run` failed because an empty `MacroDataTable` still rendered `.macro-table-state-panel` with `暂无表格行`.

Implementation notes:

- `MacroDataTable` no longer accepts the unused `state` prop and no longer renders loading or empty status panels.
- When `buildMacroTableModel(...)` produces zero displayable rows, the table primitive returns `null`.
- The dead `.macro-table-state-panel` CSS branch was removed so the empty-table compatibility surface cannot be restored by styling alone.

Green tests and checks:

- `cd web && npm run test -- tests/component/features/macro/MacroDataTable.test.tsx --run` -> 9 passed.
- `cd web && npm run test -- tests/component/features/macro/MacroDataTable.test.tsx tests/component/features/macro/MacroModulePages.test.tsx tests/component/features/macro/MacroRatesWorkbench.test.tsx tests/component/features/macro/MacroMarketBoard.test.tsx --run` -> 4 files passed, 66 tests passed.
- `cd web && npx prettier --write src/features/macro/ui/tables/MacroDataTable.tsx src/features/macro/ui/tables/macroTables.css tests/component/features/macro/MacroDataTable.test.tsx ../docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md ../docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md` -> formatted `src/features/macro/ui/tables/MacroDataTable.tsx`; other files unchanged.
- `cd web && npm run test -- tests/component/features/macro/MacroDataTable.test.tsx tests/component/features/macro/MacroModulePages.test.tsx tests/component/features/macro/MacroRatesWorkbench.test.tsx tests/component/features/macro/MacroMarketBoard.test.tsx tests/unit/features/macro/model/macroTableColumns.test.ts --run` -> 5 files passed, 72 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run format:check` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_macro_no_compatibility_contract.py -q` -> 16 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture harness 13 files passed, 73 tests passed.
- `cd web && npm run test:e2e -- tests/e2e/golden-paths/macro-responsive-audit.spec.ts --project=desktop-1366` -> 1 passed; Vite emitted the existing chunk-size warning.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check` -> pass.
- `git diff --check` -> pass.
- `rg -n "macro-table-state-panel|暂无表格行|表格加载中|state=\"loading\"|state\\?: \"idle\"" web/src/features/macro web/tests/component/features/macro web/tests/unit/features/macro/model` -> only the negative assertion in `MacroDataTable.test.tsx` remains.
- `rg -n "暂无可绘制走廊数据|暂无可绘制序列|暂无收益率曲线数据|暂无相关性矩阵数据|暂无表格行" web/src/features/macro/ui/pages web/src/features/macro/ui/rates web/src/features/macro/ui/assets web/src/features/macro/ui/workbench web/src/features/macro/ui/tables` -> no matches.

## 2026-06-17 Continuation — Generic Chart Empty State Hard Cut

Red tests:

- `cd web && npm run test -- tests/component/features/macro/MacroCharts.test.tsx --run` failed because an empty `MacroTimeSeriesChart` still rendered a figure and `暂无可绘制序列`.
- The same test failed because an empty `MacroYieldCurveChart` still rendered a figure and `暂无收益率曲线数据`; the heatmap assertion was queued behind that first failure in the same behavior group.

Implementation notes:

- `MacroTimeSeriesChart` now returns `null` when there are no drawable series and no explicit source-backed chart status label.
- Time-series status labels for real backend states, such as insufficient history or minimum-point requirements, remain visible.
- `MacroYieldCurveChart` returns `null` when the curve model has no points.
- `MacroHeatmap` returns `null` when the heatmap model has no rows.

Green tests and checks:

- `cd web && npm run test -- tests/component/features/macro/MacroCharts.test.tsx --run` -> 9 passed.
- `cd web && npm run test -- tests/component/features/macro/MacroCharts.test.tsx tests/component/features/macro/MacroModulePages.test.tsx tests/component/features/macro/MacroMarketBoard.test.tsx tests/component/features/macro/MacroRatesWorkbench.test.tsx tests/unit/features/macro/model/macroChartModel.test.ts --run` -> 5 files passed, 73 tests passed.
- `cd web && npx prettier --write src/features/macro/ui/charts/MacroTimeSeriesChart.tsx src/features/macro/ui/charts/MacroYieldCurveChart.tsx src/features/macro/ui/charts/MacroHeatmap.tsx tests/component/features/macro/MacroCharts.test.tsx ../docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md ../docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md` -> all touched files unchanged.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run format:check` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_macro_no_compatibility_contract.py -q` -> 16 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture harness 13 files passed, 73 tests passed.
- `cd web && npm run test:e2e -- tests/e2e/golden-paths/macro-responsive-audit.spec.ts --project=desktop-1366` -> 1 passed; Vite emitted the existing chunk-size warning.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check` -> pass.
- `git diff --check` -> pass.
- `rg -n "暂无可绘制序列|暂无收益率曲线数据|暂无相关性矩阵数据|chart_series_missing|yield_curve_points_missing|heatmap_rows_missing" web/src/features/macro/ui web/tests/component/features/macro` -> source code has no matches; remaining matches are negative assertions in component tests.
- `rg -n "macro-chart-state-panel" web/src/features/macro/ui/charts web/tests/component/features/macro/MacroCharts.test.tsx` -> remains only for source-backed time-series status labels such as insufficient history.

## 2026-06-17 Continuation — Correlation Empty Surface Hard Cut

Red tests:

- `cd web && npm run test -- tests/component/features/macro/MacroCorrelationTables.test.tsx --run` failed because an empty correlation matrix still rendered `暂无可用资产`.
- The same test failed because an empty pair list still rendered `暂无可用配对`.

Implementation notes:

- `MacroCorrelationMatrixTable` now returns `null` when there are no assets or no matrix rows.
- `MacroCorrelationPairList` now returns `null` when there are no pairs.
- The unused `emptyLabel` prop and dead `.macro-correlation-empty` CSS branch were deleted.

Green tests and checks:

- `cd web && npm run test -- tests/component/features/macro/MacroCorrelationTables.test.tsx --run` -> 2 passed.
- `cd web && npm run test -- tests/component/features/macro/MacroCorrelationTables.test.tsx tests/component/features/macro/MacroModulePages.test.tsx tests/unit/features/macro/model/macroCorrelationModel.test.ts --run` -> 3 files passed, 38 tests passed.
- `cd web && npx prettier --write src/features/macro/ui/correlation/MacroCorrelationTables.tsx src/features/macro/ui/correlation/macroCorrelation.css tests/component/features/macro/MacroCorrelationTables.test.tsx ../docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md ../docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md` -> all touched files unchanged.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run format:check` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_macro_no_compatibility_contract.py -q` -> 16 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture harness 13 files passed, 73 tests passed.
- `cd web && npm run test:e2e -- tests/e2e/golden-paths/macro-responsive-audit.spec.ts --project=desktop-1366` -> 1 passed; Vite emitted the existing chunk-size warning.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check` -> pass.
- `git diff --check` -> pass.
- `rg -n "暂无可用资产|暂无可用配对|macro-correlation-empty|emptyLabel" web/src/features/macro web/tests/component/features/macro web/tests/unit/features/macro/model` -> source code has no matches; remaining matches are negative assertions in component tests.
- `rg -n "暂无相关性样本|暂无可用资产|暂无可用配对|暂无" web/src/features/macro/ui/correlation web/src/features/macro/ui/assets web/src/features/macro/ui/pages/MacroAssetOverviewPage.tsx` -> no related product-copy matches; remaining match is an input filter in `AssetDiagnosticsBoard`.

## 2026-06-17 Continuation — Supporting Table Empty Shell Hard Cut

Red test:

- `cd web && npm run test -- tests/unit/features/macro/model/macroModulePresentation.test.ts --run` failed because `primarySupportingTable({ tables: [] })` still returned `{ id: "assets/equities_supporting_table", rows: [], status: "missing" }`.

Implementation notes:

- `primarySupportingTable` now returns `null` when the backend payload has no table.
- Overview and leaf pages pass `null` to `MacroMarketBoard` unless a real table has rows.
- Asset market grouping accepts a missing table and returns no groups instead of depending on a fabricated table.
- The unused `emptyTable` and `emptyChart` factories were deleted.

Green tests and checks:

- `cd web && npm run test -- tests/unit/features/macro/model/macroModulePresentation.test.ts --run` -> 8 passed.
- `cd web && npm run test -- tests/unit/features/macro/model/macroModulePresentation.test.ts tests/unit/features/macro/model/macroAssetOverviewModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx tests/component/features/macro/MacroMarketBoard.test.tsx --run` -> 4 files passed, 46 tests passed.
- `cd web && npx prettier --write src/features/macro/model/macroModulePresentation.ts src/features/macro/model/macroAssetOverviewModel.ts src/features/macro/model/macroModulePageModel.ts src/features/macro/ui/pages/MacroOverviewModulePage.tsx src/features/macro/ui/pages/MacroLeafModulePage.tsx tests/unit/features/macro/model/macroModulePresentation.test.ts ../docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md ../docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md` -> all touched files unchanged.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run format:check` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_macro_no_compatibility_contract.py -q` -> 16 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture harness 13 files passed, 73 tests passed.
- `cd web && npm run test:e2e -- tests/e2e/golden-paths/macro-responsive-audit.spec.ts --project=desktop-1366` -> 1 passed; Vite emitted the existing chunk-size warning.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check` -> pass.
- `git diff --check` -> pass.
- `rg -n "emptyTable\\(|emptyChart\\(|_supporting_table|status: \"missing\"|暂无表格行|表格加载中" web/src/features/macro web/tests/unit/features/macro/model web/tests/component/features/macro docs/sdd/features/active/2026-06-16-macro-decision-console` -> no product-code matches; remaining hits are negative assertions or SDD records.

## 2026-06-17 Continuation — Frontend Unknown Identifier Hard Cut

Red tests:

- `cd web && npm run test -- tests/unit/features/macro/model/macroModulePageModel.test.ts tests/unit/features/macro/model/macroChartModel.test.ts tests/unit/features/macro/model/macroTableColumns.test.ts --run` failed because missing chart/table ids still became `unknown_chart` and `unknown_table`, and those models still retained renderable data.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_macro_no_compatibility_contract.py -q` failed because macro runtime source still contained `unknown_chart` and `unknown_table`.

Implementation notes:

- `chartIdentifier`, `tableIdentifier`, `chartCaption`, and `tableCaption` now return `null` for missing backend ids.
- `buildMacroTimeSeriesModel`, `buildMacroYieldCurveModel`, and `buildMacroTableModel` return empty models when the chart/table id is missing.
- Macro market, rates, and asset diagnostic table callers now skip blocks whose caption cannot be derived from a real backend id.
- Rates primary visuals require a real `chartTitle`; invalid chart payloads no longer produce an empty heading or loading label.
- The macro architecture guard now rejects `unknown_chart` and `unknown_table` in runtime source.

Green tests and checks:

- `cd web && npm run test -- tests/unit/features/macro/model/macroModulePageModel.test.ts tests/unit/features/macro/model/macroChartModel.test.ts tests/unit/features/macro/model/macroTableColumns.test.ts --run` -> 3 files passed, 17 tests passed.
- `cd web && npm run test -- tests/unit/features/macro/model/macroModulePageModel.test.ts tests/unit/features/macro/model/macroChartModel.test.ts tests/unit/features/macro/model/macroTableColumns.test.ts tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts --run` -> 4 files passed, 25 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run test -- tests/component/features/macro/MacroMarketBoard.test.tsx tests/component/features/macro/MacroDataTable.test.tsx tests/component/features/macro/MacroRatesWorkbench.test.tsx tests/component/features/macro/MacroModulePages.test.tsx --run` -> 4 files passed, 66 tests passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_macro_no_compatibility_contract.py -q` -> 18 passed.
- `rg -n "unknown_chart|unknown_table" web/src/features/macro src/parallax/domains/macro_intel tests/architecture/test_macro_no_compatibility_contract.py web/tests/unit/features/macro/model web/tests/component/features/macro` -> no runtime source matches; remaining hits are architecture tokens and negative assertions.
- `cd web && npx prettier --write src/features/macro/model/macroModulePageModel.ts src/features/macro/model/macroChartModel.ts src/features/macro/model/macroTableColumns.ts src/features/macro/model/macroRatesWorkbenchModel.ts src/features/macro/ui/pages/MacroMarketBoard.tsx src/features/macro/ui/pages/MacroPrimarySeries.ts src/features/macro/ui/assets/AssetDiagnosticsBoard.tsx src/features/macro/ui/rates/RatesDetailTables.tsx src/features/macro/ui/rates/RatesDiagnosticsPanel.tsx src/features/macro/ui/rates/RatesPrimaryVisual.tsx tests/unit/features/macro/model/macroModulePageModel.test.ts tests/unit/features/macro/model/macroChartModel.test.ts tests/unit/features/macro/model/macroTableColumns.test.ts tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts ../docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md ../docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md` -> all touched files unchanged.
- `cd web && npm run test -- tests/unit/features/macro/model/macroModulePageModel.test.ts tests/unit/features/macro/model/macroChartModel.test.ts tests/unit/features/macro/model/macroTableColumns.test.ts tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts tests/component/features/macro/MacroMarketBoard.test.tsx tests/component/features/macro/MacroDataTable.test.tsx tests/component/features/macro/MacroRatesWorkbench.test.tsx tests/component/features/macro/MacroModulePages.test.tsx --run` -> 8 files passed, 91 tests passed.
- `cd web && npm run format:check` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture harness 13 files passed, 73 tests passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check` -> pass.
- `git diff --check` -> pass.
- `cd web && npm run test:e2e -- tests/e2e/golden-paths/macro-responsive-audit.spec.ts --project=desktop-1366` -> 1 passed; Vite emitted the existing chunk-size warning and a transient Vite websocket `ECONNRESET`, but the Playwright audit passed.
- `rg -n "unknown_chart|unknown_table|未命名指标|_empty_chart|emptyTable\\(|emptyChart\\(|_supporting_table" src/parallax/domains/macro_intel src/parallax/app/surfaces/api/routes_macro.py src/parallax/app/surfaces/cli/commands/macro.py web/src/features/macro web/src/routes/macro.route.tsx web/src/features/cockpit/ui/appNavigation.ts tests/architecture/test_macro_no_compatibility_contract.py tests/unit/domains/macro_intel web/tests/unit/features/macro/model web/tests/component/features/macro` -> no runtime source matches; remaining hits are architecture tokens and negative assertions.

## 2026-06-17 Continuation — Backend Generic Metadata Fallback Hard Cut

Red tests:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_feature_unit_label_requires_feature_or_metadata_unit -q` failed because a feature with no feature or concept `unit_label` still projected `单位未标注`.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_macro_no_compatibility_contract.py -q` failed because macro runtime source still contained `单位未标注`, `宏观图表`, and `宏观表格`.

Implementation notes:

- `_feature_unit_label(...)` now requires a feature or concept `unit_label` and raises `Missing macro concept unit metadata:{concept_key}` when missing.
- `_chart_title(...)` and `_table_title(...)` now require explicit title mappings and raise metadata contract errors for unknown spec ids.
- The macro architecture guard now rejects the three generic metadata fallback strings in runtime source.

Green tests and checks:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_feature_unit_label_requires_feature_or_metadata_unit tests/unit/domains/macro_intel/test_macro_module_views.py::test_feature_label_and_unit_fallback_use_metadata_not_raw_keys_or_units tests/unit/domains/macro_intel/test_macro_module_views.py::test_module_view_uses_semantic_chart_table_titles_for_every_catalog_spec -q` -> 3 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_macro_no_compatibility_contract.py -q` -> 18 passed.
- `rg -n "单位未标注|宏观图表|宏观表格" src/parallax/domains/macro_intel src/parallax/app/surfaces/api/routes_macro.py src/parallax/app/surfaces/cli/commands/macro.py web/src/features/macro web/src/routes/macro.route.tsx web/src/features/cockpit/ui/appNavigation.ts tests/architecture/test_macro_no_compatibility_contract.py tests/unit/domains/macro_intel` -> no runtime source matches; remaining hits are architecture tokens.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/test_api_macro_contract.py tests/unit/test_cli_macro_commands.py tests/architecture/test_macro_no_compatibility_contract.py -q` -> 229 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/architecture/test_macro_no_compatibility_contract.py` -> 3 files already formatted.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/architecture/test_macro_no_compatibility_contract.py` -> all checks passed.
- `cd web && npx prettier --write ../docs/sdd/features/active/2026-06-16-macro-decision-console/tasks.md ../docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md` -> all touched SDD files unchanged.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check` -> pass.
- `git diff --check` -> pass.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run format:check` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture harness 13 files passed, 73 tests passed.
- `rg -n "单位未标注|宏观图表|宏观表格|unknown_chart|unknown_table|未命名指标|_empty_chart|emptyTable\\(|emptyChart\\(|_supporting_table" src/parallax/domains/macro_intel src/parallax/app/surfaces/api/routes_macro.py src/parallax/app/surfaces/cli/commands/macro.py web/src/features/macro web/src/routes/macro.route.tsx web/src/features/cockpit/ui/appNavigation.ts` -> no runtime source matches.

## 2026-06-17 Continuation — Backend Provider Label Fallback Hard Cut

Red tests:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_module_view_provenance_requires_public_provider_metadata -q` initially failed because an unmapped `internal_feed` source still projected `未知来源` instead of raising a metadata contract error.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_macro_no_compatibility_contract.py -q` initially failed because macro runtime source still contained `未知来源`.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py -q` exposed legitimate provider aliases that needed explicit labels (`ny_fed`, `treasury`, `okx`, `deribit`) and one test-only `fixture` source that was removed from the fixture data instead of added to production metadata.

Implementation notes:

- `_provider_label(...)` now raises `Missing macro provider label metadata: {source}` for every non-empty provider name that lacks explicit public metadata.
- `_source_label(...)` returns `None` only for rows with no source name, which keeps missing-observation availability rows from manufacturing a label.
- The retained provider aliases used by current macro modules now have explicit labels: `ny_fed`, `nyfed`, `treasury`, `treasury_auction`, `treasury_fiscal`, `okx`, `deribit`, `cboe`, `coinglass`, `cftc`, `fred`, `official_fed_text`, `official_calendar`, `macro_import`, and `yahoo`.
- The macro architecture guard now rejects `未知来源` in runtime source.

Green tests and checks:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py -q` -> 101 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/test_api_macro_contract.py tests/unit/test_cli_macro_commands.py tests/architecture/test_macro_no_compatibility_contract.py -q` -> 229 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/architecture/test_macro_no_compatibility_contract.py` -> 3 files already formatted.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/architecture/test_macro_no_compatibility_contract.py` -> all checks passed.
- `rg -n "未知来源|单位未标注|宏观图表|宏观表格|unknown_chart|unknown_table|未命名指标|_empty_chart|emptyTable\\(|emptyChart\\(|_supporting_table" src/parallax/domains/macro_intel src/parallax/app/surfaces/api/routes_macro.py src/parallax/app/surfaces/cli/commands/macro.py web/src/features/macro web/src/routes/macro.route.tsx web/src/features/cockpit/ui/appNavigation.ts` -> no runtime source matches.

## 2026-06-17 Continuation — Unknown Status/Regime Fallback Hard Cut

Red tests:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_module_view_requires_known_snapshot_status_metadata tests/unit/domains/macro_intel/test_macro_module_views.py::test_module_view_requires_known_feature_quality_metadata tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_transmission_requires_known_regime_metadata -q` initially failed because unknown snapshot status, feature quality, and transmission regime codes still rendered fallback labels instead of raising contract errors.
- `cd web && npm run test -- tests/unit/features/macro/model/macroPageViewModel.test.ts tests/unit/features/macro/model/macroTableColumns.test.ts tests/component/features/macro/MacroDataTable.test.tsx --run` initially failed because `unknown` still rendered `未知`, unmapped snapshot statuses rendered raw codes, and unmapped source statuses rendered `未知状态`.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_macro_no_compatibility_contract.py -q` initially failed because macro runtime source still contained `未知`, `未知状态`, and `未知宏观状态`.

Implementation notes:

- `_status_label(...)`, `_status_key(...)`, `_quality_label(...)`, and `_regime_label(...)` now require explicit metadata and raise `Missing macro ... label metadata` errors for unmapped codes.
- Legitimate current regime aliases now have labels: `risk_on`, `risk_off_confirmation`, `low_quality_stress`, and `corridor_drain`.
- API contract fixtures now provide explicit `data_quality: ok` where they construct backend module-view features.
- Frontend page/table/source formatters drop `unknown` or unmapped source status values instead of rendering fallback placeholder labels; source rows with no audit cells are removed with the existing subtraction path.
- `macroStatusLabel(...)`, rates diagnostics, and asset diagnostics now allow nullable status labels so missing display metadata does not force a placeholder.
- The macro architecture guard now rejects bare `未知`, `未知状态`, and `未知宏观状态` in runtime source.

Green tests and checks:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_module_view_provenance_requires_public_provider_metadata tests/unit/domains/macro_intel/test_macro_module_views.py::test_module_view_requires_known_snapshot_status_metadata tests/unit/domains/macro_intel/test_macro_module_views.py::test_module_view_requires_known_feature_quality_metadata tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_transmission_requires_known_regime_metadata -q` -> 4 passed.
- `cd web && npm run test -- tests/unit/features/macro/model/macroPageViewModel.test.ts tests/unit/features/macro/model/macroTableColumns.test.ts tests/component/features/macro/MacroDataTable.test.tsx --run` -> 3 files passed, 29 tests passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_macro_no_compatibility_contract.py -q` -> 18 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_catalog.py tests/unit/test_api_macro_contract.py tests/unit/test_cli_macro_commands.py tests/architecture/test_macro_no_compatibility_contract.py -q` -> 232 passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run test -- tests/unit/features/macro/model/macroPageViewModel.test.ts tests/unit/features/macro/model/macroTableColumns.test.ts tests/component/features/macro/MacroDataTable.test.tsx tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts tests/unit/features/macro/model/macroAssetOverviewModel.test.ts tests/component/features/macro/MacroRatesWorkbench.test.tsx tests/component/features/macro/MacroModulePages.test.tsx --run` -> 7 files passed, 94 tests passed.
- `rg -n "未知|未知状态|未知宏观状态" src/parallax/domains/macro_intel src/parallax/app/surfaces/api/routes_macro.py src/parallax/app/surfaces/cli/commands/macro.py web/src/features/macro web/src/routes/macro.route.tsx web/src/features/cockpit/ui/appNavigation.ts` -> no runtime source matches.

## 2026-06-17 Continuation — Decision Console Quality Blocker Hard Cut

Red test:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_decision_console_requires_labeled_quality_blockers -q` initially failed because a scenario quality blocker with only `description` still rendered as a generic `数据缺口` blocker.

Implementation notes:

- `_compact_quality_blocker(...)` now requires a non-empty `label` or `code` and raises `Missing macro quality blocker label metadata` for unlabeled blocker payloads.
- Existing data-health-derived blockers continue to work because they already carry code, label, description/remediation, and severity.

Green tests and checks:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_decision_console_requires_labeled_quality_blockers tests/unit/domains/macro_intel/test_macro_module_views.py::test_non_overview_module_view_does_not_reuse_global_scenario_or_blockers tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_decision_console_adds_watchlist_alerts_from_trade_map_and_rules -q` -> 3 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py -q` -> 105 passed.

## 2026-06-17 Continuation — Signal Diagnostics Heading Fallback Hard Cut

Red test:

- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts --run` initially failed because `buildMacroVolatilityDiagnostics(...)` still rendered a diagnostics model headed `波动率诊断 · 期限 Contango` when the backend `volatility_diagnostics.label` was removed.

Implementation notes:

- `buildSignalDiagnostics(...)` no longer accepts a frontend `fallbackLabel`; payloads without a backend `label` return `null`.
- `MacroSignalDiagnosticsPanel` now derives its region label from `diagnostics.label`.
- Macro asset and leaf pages no longer pass fixed diagnostic aria labels such as `跨资产诊断`, `资产分项诊断`, `流动性诊断`, or `波动率诊断`.

Green tests and checks:

- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts --run` -> 1 file passed, 25 tests passed.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx tests/component/features/macro/MacroRatesWorkbench.test.tsx tests/unit/features/macro/model/macroPageViewModel.test.ts tests/unit/features/macro/model/macroTableColumns.test.ts tests/component/features/macro/MacroDataTable.test.tsx --run` -> 6 files passed, 109 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture harness 13 files passed, 73 tests passed.
- `rg -n "fallbackLabel|ariaLabel=\\\"(跨资产诊断|资产分项诊断|信用压力诊断|就业诊断|增长诊断|波动率诊断|流动性诊断|通胀诊断)\\\"|\\?\\? \\\"(跨资产诊断|资产分项诊断|信用压力诊断|就业诊断|增长诊断|波动率诊断|流动性诊断|通胀诊断)\\\"" web/src/features/macro web/tests/unit/features/macro/model/macroWorkbenchModel.test.ts web/tests/component/features/macro web/tests/fixtures/macroFixture.ts` -> no matches.

## 2026-06-17 Continuation — Signal Diagnostics Synthetic Row Key Hard Cut

Red test:

- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts --run` initially failed because a volatility diagnostics row without backend `key` still rendered with synthetic id `volatility_diagnostics:0`.

Implementation notes:

- `buildSignalDiagnostics(...)` no longer passes `payloadKey:index` fallback ids into row builders.
- Asset, volatility, credit, liquidity, employment, growth, and inflation diagnostic row parsers now require a backend `key`.
- Liquidity-pressure driver formatting reuses the stricter liquidity row parser and no longer supplies a synthetic driver id.

Green tests and checks:

- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts --run` -> 1 file passed, 26 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx tests/component/features/macro/MacroRatesWorkbench.test.tsx tests/unit/features/macro/model/macroPageViewModel.test.ts tests/unit/features/macro/model/macroTableColumns.test.ts tests/component/features/macro/MacroDataTable.test.tsx --run` -> 6 files passed, 110 tests passed.
- `cd web && npm run lint` -> ESLint passed; architecture harness 13 files passed, 73 tests passed.
- `rg -n "rowBuilder: \\(row: MacroSemanticRecord, fallbackKey|liquidityPressureDriver\\([^\\n]+fallback|volatility_diagnostics:0|asset_diagnostics:[0-9]|credit_diagnostics:[0-9]|growth_diagnostics:[0-9]|employment_diagnostics:[0-9]|liquidity_diagnostics:[0-9]|inflation_diagnostics:[0-9]" web/src/features/macro web/tests/unit/features/macro/model/macroWorkbenchModel.test.ts web/tests/component/features/macro web/tests/fixtures/macroFixture.ts` -> no runtime source matches; remaining hit is the negative assertion in the unit test.

## 2026-06-17 Continuation — Market Event Flow Identity Hard Cut

Red test:

- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts --run` initially failed because a `market_event_flow` payload without backend `key`/`label` still rendered with frontend `market_event_flow` / `市场事件流`, and a row without backend `key` still rendered as `market-event:0`.

Implementation notes:

- `buildMacroMarketEventFlow(...)` now requires backend `key` and `label` before rendering the event-flow surface.
- `marketEventFlowItem(...)` now requires a backend row `key`; rows missing keys are dropped.
- The event-flow parser no longer receives or emits `market-event:{index}` synthetic ids.

Green tests and checks:

- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts --run` -> 1 file passed, 28 tests passed.
- `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx tests/component/features/macro/MacroDriverBoard.test.tsx --run` -> 2 files passed, 35 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx tests/component/features/macro/MacroDriverBoard.test.tsx tests/component/features/macro/MacroRatesWorkbench.test.tsx tests/component/features/macro/MacroDataTable.test.tsx --run` -> 5 files passed, 93 tests passed.
- `rg -n "market-event:|market_event_flow\\\"\\)|\\?\\? \\\"market_event_flow\\\"|\\?\\? \\\"市场事件流\\\"|市场事件流" web/src/features/macro web/tests/unit/features/macro/model/macroWorkbenchModel.test.ts web/tests/component/features/macro web/tests/fixtures/macroFixture.ts` -> no runtime source fallback matches; remaining `市场事件流` hits are backend fixture/component assertions and remaining `market-event:0` hit is the negative unit-test assertion.

## 2026-06-17 Continuation — Decision Console Top/Quality Key Hard Cut

Red test:

- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts --run` initially failed because a top-change row without backend `code` still rendered with synthetic key `top:0`; the same test also covered quality blockers so `quality:0` cannot survive.

Implementation notes:

- `decisionItem(...)` now requires backend `code` and no longer accepts a `top:{index}` fallback key.
- `qualityItem(...)` now requires backend `code` and no longer accepts a `quality:{index}` fallback key.
- Sparse decision-console fixture rows that are meant to remain visible now include explicit backend-like codes.

Green tests and checks:

- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts --run` -> 1 file passed, 29 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx tests/component/features/macro/MacroDriverBoard.test.tsx tests/component/features/macro/MacroDataTable.test.tsx --run` -> 4 files passed, 73 tests passed.
- `cd web && npm run lint` -> ESLint passed; architecture harness 13 files passed, 73 tests passed.
- `rg -n "top:[0-9]|quality:[0-9]|decisionItem\\([^\\n]+top|qualityItem\\([^\\n]+quality|\\.map\\(\\(item, index\\) => decisionItem|\\.map\\(\\(item, index\\) => qualityItem" web/src/features/macro web/tests/unit/features/macro/model/macroWorkbenchModel.test.ts web/tests/component/features/macro web/tests/fixtures/macroFixture.ts` -> no runtime source matches; remaining hits are negative assertions in the unit test.

## 2026-06-17 Continuation — Decision Console Evidence/Credibility Identity Hard Cut

Red tests:

- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts --run` initially failed because confirmation evidence without backend `code` still rendered with synthetic key `confirm:0`.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts --run` initially failed because a future catalyst without backend `key`/`code` still rendered with synthetic key `future-catalyst:0`.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts --run` initially failed because a judgement-review section without backend `key` still rendered with frontend `judgement_review`, and rows without backend `key` could render with `judgement-review:0`.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts --run` initially failed because a data-credibility section without backend `key` still rendered with frontend `data_credibility`, and rows without backend `concept_key` could render with `data-credibility:0`.
- `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx --run` initially failed because orphan `quality_blockers` rendered under a frontend `数据可信度层` fallback when backend `data_credibility` was absent.

Implementation notes:

- `evidenceItem(...)` now requires backend `code`; confirmations and contradictions no longer receive `confirm:{index}` or `contradict:{index}` fallback keys.
- `futureCatalystItem(...)` now requires backend `key` or `code` and no longer receives `future-catalyst:{index}`.
- `judgementReviewItem(...)` requires backend section `key` and `label`; `judgementReviewRow(...)` requires backend row `key`.
- `dataCredibilityItem(...)` requires backend section `key` and `label`; `dataCredibilityRow(...)` requires backend `concept_key`.
- `MacroDecisionConsolePanel` now renders the data-credibility section only when the model contains backend-backed `dataCredibility`; quality blockers no longer create a standalone section with frontend title fallback.
- Macro frontend fixtures now include explicit backend-like identity for retained confirmation/contradiction rows and decision-console credibility sections.

Green tests and checks:

- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts --run` -> 1 file passed, 33 tests passed.
- `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx --run` -> 1 file passed, 35 tests passed.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx tests/component/features/macro/MacroDriverBoard.test.tsx tests/component/features/macro/MacroDataTable.test.tsx --run` -> 4 files passed, 78 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture harness 13 files passed, 73 tests passed.
- `cd web && npm run format:check` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check` -> pass.
- `git diff --check` -> pass.
- `rg -n "confirm:\\$\\{index\\}|contradict:\\$\\{index\\}|future-catalyst:\\$\\{index\\}|judgement-review:\\$\\{index\\}|data-credibility:\\$\\{index\\}|confirm:[0-9]|contradict:[0-9]|future-catalyst:[0-9]|judgement-review:[0-9]|data-credibility:[0-9]" web/src/features/macro web/tests/unit/features/macro/model/macroWorkbenchModel.test.ts web/tests/component/features/macro web/tests/fixtures/macroFixture.ts` -> no runtime source matches; remaining hits are negative assertions in the unit test.
- `rg -n "evidenceItem\\([^\\n]+confirm|evidenceItem\\([^\\n]+contradict|futureCatalystItem\\([^\\n]+future-catalyst|judgementReviewRow\\([^\\n]+judgement-review|dataCredibilityRow\\([^\\n]+data-credibility|credibility\\?\\.label \\?\\?|\\?\\? \\\"judgement_review\\\"|\\?\\? \\\"昨日判断复盘\\\"|\\?\\? \\\"data_credibility\\\"|\\?\\? \\\"数据可信度层\\\"" web/src/features/macro web/tests/unit/features/macro/model/macroWorkbenchModel.test.ts web/tests/component/features/macro web/tests/fixtures/macroFixture.ts` -> no matches.

## 2026-06-17 Continuation — Trade Map/Watchlist/Structured Identity Hard Cut

Red tests:

- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts --run` initially failed because a scenario case without backend `case` still rendered with synthetic key `scenario:0`.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts --run` initially failed because a watchlist section without backend `key` still rendered with frontend `watchlist_alerts`.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts --run` initially failed because a structured-analysis section without backend `key` still rendered with frontend `structured_analysis`.

Implementation notes:

- `scenarioCaseItem(...)` now requires backend `case`; the caller no longer passes `scenario:{index}`.
- `tradeMapItem(...)` now requires backend `expression`; the caller no longer passes `trade:{index}`.
- `watchlistAlertsItem(...)` now requires backend section `key` and `label`; watchlist assets require backend `key`; watchlist rules require backend `key` or `code`.
- `buildMacroStructuredAnalysis(...)` now requires backend section `key` and `label`; `structuredAnalysisRow(...)` now requires backend row `key`.
- Sparse unit-test fixtures that intentionally remain visible now carry backend-like keys instead of relying on UI fallback identity.

Green tests and checks:

- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts --run` -> 1 file passed, 36 tests passed.
- `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx tests/component/features/macro/MacroDriverBoard.test.tsx --run` -> 2 files passed, 36 tests passed.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx tests/component/features/macro/MacroDriverBoard.test.tsx tests/component/features/macro/MacroDataTable.test.tsx --run` -> 4 files passed, 81 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture harness 13 files passed, 73 tests passed.
- `cd web && npm run format:check` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check` -> pass.
- `git diff --check` -> pass.
- `rg -n "structured-analysis:\\$\\{index\\}|scenario:\\$\\{index\\}|trade:\\$\\{index\\}|watchlist-asset:\\$\\{index\\}|watchlist-rule:\\$\\{index\\}|structured-analysis:[0-9]|scenario:[0-9]|trade:[0-9]|watchlist-asset:[0-9]|watchlist-rule:[0-9]" web/src/features/macro web/tests/unit/features/macro/model/macroWorkbenchModel.test.ts web/tests/component/features/macro web/tests/fixtures/macroFixture.ts` -> no runtime source matches; remaining hits are negative assertions in the unit test.
- `rg -n "structuredAnalysisRow\\([^\\n]+structured-analysis|scenarioCaseItem\\([^\\n]+scenario|tradeMapItem\\([^\\n]+trade|watchlistAssetItem\\([^\\n]+watchlist|watchlistRuleItem\\([^\\n]+watchlist|\\?\\? \\\"structured_analysis\\\"|\\?\\? \\\"跨域判断链\\\"|\\?\\? \\\"watchlist_alerts\\\"|\\?\\? \\\"Watchlist 与触发提醒\\\"" web/src/features/macro web/tests/unit/features/macro/model/macroWorkbenchModel.test.ts web/tests/component/features/macro web/tests/fixtures/macroFixture.ts` -> no matches.

## 2026-06-17 Continuation — Decision Console Generic Copy Fallback Hard Cut

Red tests:

- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts --run` initially failed because a liquidity-pressure payload without backend `key` still rendered with frontend `liquidity_pressure` / `流动性压力`.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts --run` initially failed because Trade Map historical review without backend `label` still rendered `历史验证`, and portfolio review without backend `label` still rendered `纸面映射`.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts --run` initially failed because unmapped future-catalyst metadata still rendered generic `提示 · 事件`.

Implementation notes:

- `liquidityPressureItem(...)` now requires backend `key` and `label` before rendering.
- `tradeMapHistory(...)` and `tradeMapPortfolio(...)` now require backend review labels before rendering those subsections.
- `checklistKindLabel(...)`, `sectionLabel(...)`, `severityLabel(...)`, and `eventKindLabel(...)` return `null` for unmapped codes instead of generic product copy.
- `tradeMapChecklist(...)` drops checklist rows whose `kind` is not mapped to an explicit label.
- The macro overview fixture now carries explicit `liquidity_pressure.key`.

Green tests and checks:

- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts --run` -> 1 file passed, 39 tests passed.
- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx tests/component/features/macro/MacroDriverBoard.test.tsx tests/component/features/macro/MacroDataTable.test.tsx --run` -> 4 files passed, 84 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture harness 13 files passed, 73 tests passed.
- `cd web && npm run format:check` -> pass.
- `rg -n "\\?\\? \\\"(liquidity_pressure|流动性压力|历史验证|纸面映射|行动|宏观|提示|事件)\\\"|\\|\\| \\\"(liquidity_pressure|流动性压力|历史验证|纸面映射|行动|宏观|提示|事件)\\\"" web/src/features/macro/model/macroWorkbenchModel.ts web/tests/unit/features/macro/model/macroWorkbenchModel.test.ts web/tests/component/features/macro web/tests/fixtures/macroFixture.ts` -> no matches.
- `rg -n "历史验证|纸面映射|行动|宏观|提示|事件|流动性压力" web/src/features/macro/model/macroWorkbenchModel.ts` -> no fallback matches; remaining hits are explicit allowed mapping labels.

## 2026-06-17 Continuation — Backend Decision Console Contract Hard Cut

Red tests:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_module_view_requires_labeled_data_gap_severity_metadata -q` initially failed because mapped data-gap payloads still received implicit `warning` severity.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_module_view_requires_data_gap_remediation_metadata -q` initially failed because mapped data-gap payloads still received generic remediation copy from module-view fallback logic.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_decision_console_requires_top_change_section_metadata -q` initially failed because top-change rows missing `node` still rendered under the fallback `macro` section.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_decision_console_requires_labeled_quality_blocker_severity tests/unit/domains/macro_intel/test_macro_module_views.py::test_decision_console_requires_known_top_change_section_metadata tests/unit/domains/macro_intel/test_macro_module_views.py::test_decision_console_requires_known_watchlist_severity_metadata tests/unit/domains/macro_intel/test_macro_module_views.py::test_decision_console_requires_known_liquidity_pressure_regime_metadata tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_decision_console_adds_liquidity_pressure_from_retained_rrp_tga_diagnostics -q` initially failed because the backend still defaulted missing blocker severity to `warning`, rendered unknown top-change section codes as raw labels, mapped unknown severity to fallback labels, mapped unknown liquidity regimes to neutral score/label output, and omitted the stable `liquidity_pressure` key.

Implementation notes:

- `decision_console.liquidity_pressure` now includes `key: liquidity_pressure`.
- Mapped data gaps require explicit `code`, `label`, `severity`, and `remediation_hint`; only string gap codes may go through the canonical `build_macro_data_gaps(...)` mapping path.
- Internally generated chart-missing and insufficient-history gaps now carry explicit repair copy at the generation site.
- `_compact_quality_blocker(...)` requires explicit blocker label and severity; data-health derived blockers no longer receive an implicit `warning`.
- `_section_label(...)` now raises on unknown sections instead of returning the raw code.
- `_compact_signal(...)` requires top-change `node` metadata and no longer defaults missing nodes to `macro`.
- Watchlist and future-catalyst severity labels now require known severity metadata.
- Liquidity-pressure scoring and regime labels now require known regime metadata rather than silently outputting neutral pressure.

Green tests and checks:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_module_view_requires_labeled_data_gap_severity_metadata -q` -> 1 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_module_view_requires_data_gap_remediation_metadata -q` -> 1 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_decision_console_requires_top_change_section_metadata -q` -> 1 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_decision_console_requires_labeled_quality_blocker_severity tests/unit/domains/macro_intel/test_macro_module_views.py::test_decision_console_requires_known_top_change_section_metadata tests/unit/domains/macro_intel/test_macro_module_views.py::test_decision_console_requires_known_watchlist_severity_metadata tests/unit/domains/macro_intel/test_macro_module_views.py::test_decision_console_requires_known_liquidity_pressure_regime_metadata tests/unit/domains/macro_intel/test_macro_module_views.py::test_overview_decision_console_adds_liquidity_pressure_from_retained_rrp_tga_diagnostics -q` -> 5 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py -q` -> 112 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_macro_no_compatibility_contract.py -q` -> 18 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py` -> 2 files already formatted.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check` -> pass.
- `git diff --check` -> pass.

## 2026-06-17 Continuation — Concept Metadata Raw Fallback Hard Cut

Red tests:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py -q -k "availability_rows_require_catalog_concept_label_metadata or observation_supplements_require_catalog_unit_metadata"` initially failed because availability rows still displayed raw missing concept keys such as `rates:dgs5`, and observation supplements still displayed raw observation units such as `percent`.

Implementation notes:

- `_concept_metadata(...)`, `_concept_required_text(...)`, and `_concept_optional_text(...)` now centralize concept metadata reads.
- Observation-derived features now require catalog `label`, `short_label`, and `unit_label`.
- Availability table rows, missing-concept evidence, event labels, and `_concept_short_label(...)` now require explicit concept metadata instead of falling back to raw `concept_key`.
- `_feature_short_label(...)` no longer falls back to the long label when short-label metadata is missing.
- The macro no-compatibility architecture guard now rejects the retired raw concept metadata fallback expressions.

Green tests and checks:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py -q -k "feature_label_and_unit_fallback_use_metadata_not_raw_keys_or_units or feature_unit_label_requires_feature_or_metadata_unit or availability_rows_require_catalog_concept_label_metadata or observation_supplements_require_catalog_unit_metadata"` -> 4 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py -q` -> 114 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/architecture/test_macro_no_compatibility_contract.py -q` -> 19 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/architecture/test_macro_no_compatibility_contract.py` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py tests/architecture/test_macro_no_compatibility_contract.py` -> 3 files already formatted.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check` -> pass.
- `git diff --check` -> pass.
- `rg -n "MACRO_CONCEPT_METADATA\\.get\\(concept_key, \\{\\}\\)\\.get\\(\\\"(label|short_label)\\\"\\) or concept_key|MACRO_CONCEPT_METADATA\\.get\\(concept_key, \\{\\}\\)\\.get\\(\\\"unit_label\\\"\\) or str\\(unit or \\\"\\\"\\)|metadata\\.get\\(\\\"(label|short_label)\\\"\\) or concept_key|metadata\\.get\\(\\\"unit_label\\\"\\) or str\\(unit or \\\"\\\"\\)|metadata\\.get\\(\\\"short_label\\\"\\) or _feature_label\\(concept_key, feature\\)" src/parallax/domains/macro_intel/services/macro_module_views.py` -> no raw metadata fallback matches.

## 2026-06-17 Continuation — Frontend Model Identity Hard Cut

Red tests:

- `cd web && npm run test -- tests/unit/features/macro/model/macroModulePresentation.test.ts tests/unit/features/macro/model/macroTableColumns.test.ts tests/unit/features/macro/model/macroCorrelationModel.test.ts --run` initially failed because metrics without `concept_key` still rendered using label-derived keys, data-health gaps without `code` still rendered with bucket/index keys, table rows without `row_id` still rendered with concept/label/id/index-derived ids, and unknown correlation assets still rendered as `资产`.

Implementation notes:

- `buildMacroMetrics(...)` now requires backend `concept_key` and explicit `label`; it no longer emits `metric:${index}` or label-derived keys.
- Data-health gap items now require backend `code`; label-only gaps are dropped instead of receiving `${bucketKey}:${index}`.
- `buildMacroTableModel(...)` now requires backend `row_id` and uses it directly, without concept/symbol/label/id fallback or row-index suffixes.
- `assetLabel(...)` now returns `null` for unknown correlation assets, and the correlation matrix/pair-list UI omits rows or pairs whose labels are not in `titleByKey`.
- `web/tests/architecture/macroModelHardCut.test.ts` rejects the retired frontend identity and correlation-label fallback templates.

Green tests and checks:

- `cd web && npm run test -- tests/unit/features/macro/model/macroModulePresentation.test.ts tests/unit/features/macro/model/macroTableColumns.test.ts tests/unit/features/macro/model/macroCorrelationModel.test.ts --run` -> 3 files passed, 19 tests passed.
- `cd web && npm run test -- tests/unit/features/macro/model/macroModulePresentation.test.ts tests/unit/features/macro/model/macroTableColumns.test.ts tests/unit/features/macro/model/macroCorrelationModel.test.ts tests/component/features/macro/MacroCorrelationTables.test.tsx tests/component/features/macro/MacroDataTable.test.tsx tests/component/features/macro/MacroModulePages.test.tsx --run` -> 6 files passed, 65 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture harness 14 files passed, 74 tests passed.
- `cd web && npm run format:check` -> pass.

## 2026-06-17 Continuation — Rates Corridor Missing Concept Hard Cut

Red tests:

- `cd web && npm run test -- tests/unit/features/macro/model/macroRatesChartModel.test.ts --run` initially failed because unknown missing concepts such as `fed:not_mapped` were still exposed in `missingLabels`.
- `cd web && npm run test:architecture -- tests/architecture/macroModelHardCut.test.ts` initially failed because the retired `CORRIDOR_LABELS[CORRIDOR_SERIES_BY_CONCEPT[concept]] ?? concept` fallback was still present.

Implementation notes:

- `buildRatesCorridorModel(...)` now `flatMap`s missing concepts through `CORRIDOR_SERIES_BY_CONCEPT`.
- Known corridor concepts still produce labels such as `SOFR 30D`; unknown concepts produce no display label.
- `web/tests/architecture/macroModelHardCut.test.ts` rejects the retired raw concept fallback expression.

Green tests and checks:

- `cd web && npm run test -- tests/unit/features/macro/model/macroRatesChartModel.test.ts tests/component/features/macro/RatesCorridorChart.test.tsx tests/component/features/macro/MacroRatesWorkbench.test.tsx --run` -> 3 files passed, 28 tests passed.
- `cd web && npm run test:architecture -- tests/architecture/macroModelHardCut.test.ts` -> architecture harness 14 files passed, 74 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture harness 14 files passed, 74 tests passed.
- `cd web && npm run format:check` -> pass.

## 2026-06-17 Continuation — Source Degradation Note Hard Cut

Red tests:

- `cd web && npm run test -- tests/component/features/macro/MacroDataTable.test.tsx --run` initially failed because coded degradation reasons such as `provider_not_configured` still rendered generic `存在降级原因` notes.
- `cd web && npm run test:architecture -- tests/architecture/macroModelHardCut.test.ts` initially failed because `MacroSourceTable.tsx` still contained the retired generic degradation-note fallback.

Implementation notes:

- `notesLabel(...)` now calls `displayText(...)` without a fallback copy argument.
- `displayText(...)` returns mapped display labels, raw non-code text, or `null` for internal code-like values.
- Source tables omit the notes column when only coded degradation reasons are present.
- `web/tests/architecture/macroModelHardCut.test.ts` rejects the retired generic note text and two-argument fallback call.

Green tests and checks:

- `cd web && npm run test -- tests/component/features/macro/MacroDataTable.test.tsx tests/component/features/macro/MacroModulePages.test.tsx tests/component/features/macro/MacroRatesWorkbench.test.tsx --run` -> 3 files passed, 72 tests passed.
- `cd web && npm run test:architecture -- tests/architecture/macroModelHardCut.test.ts` -> architecture harness 14 files passed, 74 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture harness 14 files passed, 74 tests passed.
- `cd web && npm run format:check` -> pass.

## 2026-06-17 Continuation — Asset Row As-Of Fallback Hard Cut

Red tests:

- `cd web && npm run test -- tests/unit/features/macro/model/macroAssetOverviewModel.test.ts --run` initially failed because `buildAssetMarketGroups(table, "2026-05-20")` still backfilled missing row dates from the module snapshot date.
- `cd web && npm run test:architecture -- tests/architecture/macroModelHardCut.test.ts` initially failed because `macroAssetOverviewModel.ts` still contained `fallbackAsOf`.

Implementation notes:

- Removed the `fallbackAsOf` parameter from `buildAssetMarketGroups(...)`.
- Removed module-snapshot date backfill from `assetMarketRow(...)` / `asOfLabel(...)`.
- `MacroAssetOverviewPage` now calls `buildAssetMarketGroups(supportingTable)` without passing module snapshot dates.
- Added page coverage proving a missing row date does not render the module snapshot date inside the asset table.

Green tests and checks:

- `cd web && npm run test -- tests/unit/features/macro/model/macroAssetOverviewModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx --run` -> 2 files passed, 41 tests passed.
- `cd web && npm run test:architecture -- tests/architecture/macroModelHardCut.test.ts` -> architecture harness passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture harness 14 files passed, 74 tests passed.
- `cd web && npm run format:check` -> pass.

## 2026-06-17 Continuation — Driver Board Meta Fallback Hard Cut

Red tests:

- `cd web && npm run test -- tests/component/features/macro/MacroDriverBoard.test.tsx --run` initially failed because `MacroDriverBoard` still rendered `0 条证据` when no explicit panel meta was supplied.
- `cd web && npm run test:architecture -- tests/architecture/macroModelHardCut.test.ts` initially failed because the retired `meta ?? \`${drivers.evidenceCount} 条证据\`` fallback was still present.

Implementation notes:

- `MacroDriverBoard` now passes `meta` directly to `MacroPanel`.
- Missing meta produces no panel meta instead of generated evidence-count copy.
- Existing overview and leaf pages continue to pass explicit route/module meta.
- `web/tests/architecture/macroModelHardCut.test.ts` rejects the retired evidence-count fallback expression.

Green tests and checks:

- `cd web && npm run test -- tests/component/features/macro/MacroDriverBoard.test.tsx --run` -> 1 file passed, 1 test passed.
- `cd web && npm run test:architecture -- tests/architecture/macroModelHardCut.test.ts` -> architecture harness 14 files passed, 74 tests passed.
- `cd web && npm run test -- tests/component/features/macro/MacroDriverBoard.test.tsx tests/component/features/macro/MacroModulePages.test.tsx tests/routes/macro.route.test.tsx --run` -> 3 files passed, 52 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture harness 14 files passed, 74 tests passed.
- `cd web && npm run format:check` -> pass.

## 2026-06-17 Continuation — Correlation Matrix Caption Hard Cut

Red tests:

- `cd web && npm run test -- tests/component/features/macro/MacroCorrelationTables.test.tsx --run` initially failed because the matrix still rendered `60d 资产相关性矩阵` when no explicit label was supplied.
- `cd web && npm run test:architecture -- tests/architecture/macroModelHardCut.test.ts` initially failed because `MacroCorrelationMatrixTable` still contained the retired `label ?? \`${data.window} 资产相关性矩阵\`` fallback.

Implementation notes:

- `MacroCorrelationMatrixTable` now trims and requires an explicit `label`.
- Missing label returns `null` before table/frame chrome is built.
- Existing asset correlation preview still passes the deliberate `60日资产相关性矩阵` label.
- `web/tests/architecture/macroModelHardCut.test.ts` rejects the retired window-derived caption expression.

Green tests and checks:

- `cd web && npm run test -- tests/component/features/macro/MacroCorrelationTables.test.tsx --run` -> 1 file passed, 3 tests passed.
- `cd web && npm run test:architecture -- tests/architecture/macroModelHardCut.test.ts` -> architecture harness 14 files passed, 74 tests passed.
- `cd web && npm run test -- tests/component/features/macro/MacroCorrelationTables.test.tsx tests/component/features/macro/MacroModulePages.test.tsx tests/routes/macro.route.test.tsx --run` -> 3 files passed, 54 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture harness 14 files passed, 74 tests passed.
- `cd web && npm run format:check` -> pass.

## 2026-06-17 Continuation — Asset Daily Brief Fallback Hard Cut

Red tests:

- `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx --run` initially failed because the asset page still rendered `今日判断` from `module_read.summary` when `daily_brief` was absent.
- `cd web && npm run test:architecture -- tests/architecture/macroModelHardCut.test.ts` initially failed because `AssetDailyBrief` still accepted fallback headline copy and `MacroAssetOverviewPage` still passed `fallback={readSummary}`.

Implementation notes:

- `AssetDailyBrief` now requires a normalized `MacroDailyBrief` and no longer accepts `fallback`.
- `MacroAssetOverviewPage` renders the asset judgment section only when `normalizeDailyBrief(module.daily_brief)` returns a valid brief.
- Removed the asset page `macroReadSummary(module)` path from the judgment rail.
- Updated the default asset fixture with explicit `symbol` column/cell metadata so route coverage continues proving the core asset market surface under the stricter identity contract.
- `web/tests/architecture/macroModelHardCut.test.ts` rejects the retired asset daily-brief fallback expressions.

Green tests and checks:

- `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx --run` -> 1 file passed, 37 tests passed.
- `cd web && npm run test:architecture -- tests/architecture/macroModelHardCut.test.ts` -> architecture harness 14 files passed, 74 tests passed.
- `cd web && npm run test -- tests/routes/macro.route.test.tsx tests/component/features/macro/MacroModulePages.test.tsx --run` -> 2 files passed, 51 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture harness 14 files passed, 74 tests passed.
- `cd web && npm run format:check` -> pass.

## 2026-06-17 Continuation — Rates Market Explanation Dead Field Hard Cut

Red tests:

- `cd web && npm run test:architecture -- tests/architecture/macroModelHardCut.test.ts` initially failed because `macroRatesWorkbenchModel.ts` still contained `neutralFallbackExplanation(...)` and `marketExplanation`.

Implementation notes:

- Removed `RatesWorkbenchView.marketExplanation`.
- Removed the generated `marketExplanation` construction from `buildRatesWorkbenchView(...)`.
- Deleted `neutralFallbackExplanation(...)`.
- Removed unit tests and helper text aggregation that existed only for the dead explanation field.
- `web/tests/architecture/macroModelHardCut.test.ts` rejects reintroducing `neutralFallbackExplanation(...)` or `marketExplanation` in macro source files.

Green tests and checks:

- `rg -n 'neutralFallbackExplanation|marketExplanation' web/src/features/macro web/tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts` -> no matches.
- `cd web && npm run test -- tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts --run` -> 1 file passed, 16 tests passed.
- `cd web && npm run test:architecture -- tests/architecture/macroModelHardCut.test.ts` -> architecture harness 14 files passed, 74 tests passed.
- `cd web && npm run test -- tests/component/features/macro/MacroRatesWorkbench.test.tsx tests/component/features/macro/MacroModulePages.test.tsx tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts --run` -> 3 files passed, 77 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture harness 14 files passed, 74 tests passed.
- `cd web && npm run format:check` -> pass.

## 2026-06-17 Continuation — Detail Table Identity Hard Cut

Red tests:

- `cd web && npm run test -- tests/component/features/macro/MacroMarketBoard.test.tsx tests/component/features/macro/MacroRatesWorkbench.test.tsx --run` initially failed because macro board and rates detail table stacks still accepted tables without backend `id`/`title`.
- `cd web && npm run test:architecture -- tests/architecture/macroModelHardCut.test.ts` initially failed because table list keys still used `String(table.id ?? index)`.

Implementation notes:

- `MacroMarketBoard`, `RatesDetailTables`, and `RatesDiagnosticsPanel` now require backend table `id`, backend `title`, and rows before rendering table stacks.
- Empty supporting/detail panels are omitted when every table is missing backend display identity.
- `web/tests/architecture/macroModelHardCut.test.ts` rejects the retired table-index key fallback.

Green tests and checks:

- `cd web && npm run test -- tests/component/features/macro/MacroMarketBoard.test.tsx tests/component/features/macro/MacroRatesWorkbench.test.tsx --run` -> 2 files passed.
- `cd web && npm run test:architecture -- tests/architecture/macroModelHardCut.test.ts` -> pass.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture harness passed.
- `cd web && npm run format:check` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check` -> pass.
- `git diff --check` -> pass.

## 2026-06-17 Continuation — Chart Series Status And Yield Label Hard Cut

Red tests:

- `cd web && npm run test -- tests/unit/features/macro/model/macroChartModel.test.ts --run` initially failed because chart series still manufactured `ok` status and yield-curve labels from tenor metadata.
- `cd web && npm run test:architecture -- tests/architecture/macroModelHardCut.test.ts` initially failed because the retired chart-series status and yield-label fallback expressions were still present.

Implementation notes:

- `MacroChartSeriesModel.status` is now nullable and `seriesStatus(...)` returns explicit backend status, `insufficient_history` for under-sampled series, or `null`.
- Yield-curve points require backend labels; labels such as `10Y` are no longer derived from tenor metadata.
- Yield-curve fixtures now include explicit point labels.

Green tests and checks:

- `cd web && npm run test -- tests/unit/features/macro/model/macroChartModel.test.ts --run` -> pass.
- `cd web && npm run test:architecture -- tests/architecture/macroModelHardCut.test.ts` -> pass.
- `cd web && npm run test -- tests/component/features/macro/MacroCharts.test.tsx tests/component/features/macro/MacroMarketBoard.test.tsx tests/component/features/macro/MacroModulePages.test.tsx tests/unit/features/macro/model/macroChartModel.test.ts --run` -> pass.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture harness passed.
- `cd web && npm run format:check` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check` -> pass.
- `git diff --check` -> pass.

## 2026-06-17 Continuation — Rates Diagnostics Label Hard Cut

Red tests:

- `cd web && npm run test -- tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts --run` initially failed because policy, curve, and real-rate diagnostics still rendered default frontend section labels when backend labels were absent.
- `cd web && npm run test:architecture -- tests/architecture/macroModelHardCut.test.ts` initially failed because the retired rates diagnostics default-label expressions were still present.

Implementation notes:

- `buildPolicyDiagnostics(...)`, `buildCurveDiagnostics(...)`, and `buildRealRateDiagnostics(...)` now require explicit backend `label` metadata.
- Missing diagnostics labels remove the diagnostics block instead of inserting `政策走廊诊断`, `曲线诊断`, or `实际利率诊断`.
- `web/tests/architecture/macroModelHardCut.test.ts` rejects the retired default-label expressions.

Green tests and checks:

- `cd web && npm run test -- tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts --run` -> pass.
- `cd web && npm run test:architecture -- tests/architecture/macroModelHardCut.test.ts` -> pass.
- `cd web && npm run test -- tests/component/features/macro/MacroRatesWorkbench.test.tsx tests/component/features/macro/MacroModulePages.test.tsx tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts --run` -> pass.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture harness passed.
- `cd web && npm run format:check` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check` -> pass.
- `git diff --check` -> pass.

## 2026-06-17 Continuation — Rates Market Headline Hard Cut

Red tests:

- `cd web && npm run test -- tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts tests/component/features/macro/MacroRatesWorkbench.test.tsx --run` initially failed because the rates model still generated `政策利率走廊：部分可用` and the UI still rendered a `利率简报` region without backend headline copy.
- `cd web && npm run test:architecture -- tests/architecture/macroModelHardCut.test.ts` initially failed because the retired `readHeadline ?? ... readinessLabel(...)` fallback expression was still present.

Implementation notes:

- `RatesWorkbenchView.marketHeadline` is now nullable and is populated only from sanitized backend `module_read.headline`.
- `RatesMarketRead` returns `null` when the backend omits a market headline, instead of rendering an empty headline panel.
- The unit-test text helper now accepts nullable `marketHeadline` so tests do not reintroduce the old string contract.

Green tests and checks:

- `cd web && npm run test -- tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts tests/component/features/macro/MacroRatesWorkbench.test.tsx --run` -> 2 files passed.
- `cd web && npm run test:architecture -- tests/architecture/macroModelHardCut.test.ts` -> architecture harness 14 files passed, 74 tests passed.
- `cd web && npm run test -- tests/component/features/macro/MacroRatesWorkbench.test.tsx tests/component/features/macro/MacroModulePages.test.tsx tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts --run` -> pass.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture harness 14 files passed, 74 tests passed.
- `cd web && npm run format:check` -> pass.

## 2026-06-17 Continuation — Chart/Table Caption Hard Cut

Red tests:

- `cd web && npm run test -- tests/unit/features/macro/model/macroModulePageModel.test.ts --run` initially failed because chart/table captions were still derived from backend ids such as `yield_curve`.
- `cd web && npm run test:architecture -- tests/architecture/macroModelHardCut.test.ts` initially failed because `TITLE_BY_ID`, `labelFromIdentifier(...)`, `WORD_LABELS`, and id splitting were still present.

Implementation notes:

- `chartCaption(...)` now returns only explicit backend `chart.title`.
- `tableCaption(...)` now returns only explicit backend `table.title`.
- Removed `TITLE_BY_ID`, `labelFromIdentifier(...)`, and `WORD_LABELS`.
- `web/tests/architecture/macroModelHardCut.test.ts` rejects the retired caption fallback paths.

Green tests and checks:

- `cd web && npm run test -- tests/unit/features/macro/model/macroModulePageModel.test.ts --run` -> 1 file passed, 2 tests passed.
- `cd web && npm run test:architecture -- tests/architecture/macroModelHardCut.test.ts` -> architecture harness 14 files passed, 74 tests passed.
- `cd web && npm run test -- tests/component/features/macro/MacroCharts.test.tsx tests/component/features/macro/MacroModulePages.test.tsx tests/component/features/macro/MacroRatesWorkbench.test.tsx tests/component/features/macro/MacroDataTable.test.tsx --run` -> 4 files passed, 78 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture harness 14 files passed, 74 tests passed.
- `cd web && npm run format:check` -> pass.
- `rg -n 'TITLE_BY_ID|labelFromIdentifier|WORD_LABELS|\\.split\\("_"\\)' web/src/features/macro` -> no matches.

## 2026-06-17 Continuation — Driver Board Identity Hard Cut

Red tests:

- `cd web && npm run test -- tests/component/features/macro/MacroDriverBoard.test.tsx tests/unit/features/macro/model/macroModulePresentation.test.ts --run` initially failed because transmission nodes still rendered from `kind`/`status_label` or missing keys, and evidence items without backend identity still rendered.
- `cd web && npm run test:architecture -- tests/architecture/macroModelHardCut.test.ts` initially failed because the driver board still contained kind/status/index fallback expressions.

Implementation notes:

- Added optional `key` to `MacroTransmissionNode` and required it at render time.
- `MacroDriverBoard` now requires transmission `key`, `label`, and `value`; it no longer falls back to `kind`, `status_label`, or `status`.
- `MacroEvidenceGroup` items now include stable `key`, derived from backend evidence `code`/`key`.
- Evidence items without backend identity are dropped by `buildMacroEvidenceGroups(...)`.
- Macro fixtures now include explicit codes for previously unlabeled watch/invalidations and `key` for transmission rows.
- `web/tests/architecture/macroModelHardCut.test.ts` rejects the retired driver board fallback expressions.

Green tests and checks:

- `cd web && npm run test -- tests/component/features/macro/MacroDriverBoard.test.tsx tests/unit/features/macro/model/macroModulePresentation.test.ts tests/unit/features/macro/model/macroPageViewModel.test.ts --run` -> 3 files passed, 24 tests passed.
- `cd web && npm run test:architecture -- tests/architecture/macroModelHardCut.test.ts` -> architecture harness 14 files passed, 74 tests passed.
- `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx tests/component/features/macro/MacroDriverBoard.test.tsx tests/unit/features/macro/model/macroModulePresentation.test.ts tests/unit/features/macro/model/macroPageViewModel.test.ts --run` -> 4 files passed, 61 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture harness 14 files passed, 74 tests passed.
- `cd web && npm run format:check` -> pass.
- `rg -n 'node\\.label \\?\\? node\\.kind|node\\.value \\?\\? node\\.status_label \\?\\? node\\.status|`\\$\\{node\\.label \\?\\? node\\.kind \\?\\? "node"\\}:\\$\\{index\\}`|`\\$\\{group\\.key\\}:\\$\\{item\\.label\\}:\\$\\{index\\}`' web/src/features/macro` -> no matches.

## 2026-06-17 Continuation — Detail Table Identity Hard Cut

Red tests:

- `cd web && npm run test -- tests/component/features/macro/MacroMarketBoard.test.tsx tests/component/features/macro/MacroRatesWorkbench.test.tsx --run` initially failed because missing-id/title tables still left empty `主市场证据` / `利率明细` panels.
- `cd web && npm run test:architecture -- tests/architecture/macroModelHardCut.test.ts` initially failed because `MacroMarketBoard`, `RatesDetailTables`, and `RatesDiagnosticsPanel` still used `String(table.id ?? index)`.

Implementation notes:

- `MacroMarketBoard` filters supporting tables through backend `id`, backend `title`, and row presence before rendering.
- `RatesDetailTables` filters primary detail tables through backend `id`, backend `title`, and row presence before rendering.
- `RatesDiagnosticsPanel` applies the same identity/title contract to diagnostic detail tables.
- Table list keys now use backend `table.id` only.
- `web/tests/architecture/macroModelHardCut.test.ts` rejects the retired table-index key fallback.

Green tests and checks:

- `cd web && npm run test -- tests/component/features/macro/MacroMarketBoard.test.tsx tests/component/features/macro/MacroRatesWorkbench.test.tsx --run` -> 2 files passed, 26 tests passed.
- `cd web && npm run test:architecture -- tests/architecture/macroModelHardCut.test.ts` -> architecture harness 14 files passed, 74 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture harness 14 files passed, 74 tests passed.
- `cd web && npm run format:check` -> pass.
- `rg -n 'String\\(table\\.id \\?\\? index\\)|table\\.id \\?\\? index' web/src/features/macro` -> no matches.

## 2026-06-17 Continuation — Chart Series Status And Yield Label Hard Cut

Red tests:

- `cd web && npm run test -- tests/unit/features/macro/model/macroChartModel.test.ts --run` initially failed because renderable chart series still received `status: "ok"` without backend status metadata, and unlabeled yield-curve series still generated labels such as `10Y`.
- `cd web && npm run test:architecture -- tests/architecture/macroModelHardCut.test.ts` initially failed because `macroChartModel.ts` still contained `return explicit ?? "ok";` and `` `${tenorYears}Y` ``.

Implementation notes:

- `MacroChartSeriesModel.status` is now nullable.
- `seriesStatus(...)` returns explicit backend/payload status or `insufficient_history`; otherwise it returns `null`.
- Yield-curve points now require backend labels before rendering.
- Updated chart component fixtures to provide explicit yield labels.
- `web/tests/architecture/macroModelHardCut.test.ts` rejects the retired chart series status and yield-label fallbacks.

Green tests and checks:

- `cd web && npm run test -- tests/unit/features/macro/model/macroChartModel.test.ts --run` -> 1 file passed, 11 tests passed.
- `cd web && npm run test:architecture -- tests/architecture/macroModelHardCut.test.ts` -> architecture harness 14 files passed, 74 tests passed.
- `cd web && npm run test -- tests/component/features/macro/MacroCharts.test.tsx tests/component/features/macro/MacroMarketBoard.test.tsx tests/component/features/macro/MacroModulePages.test.tsx tests/unit/features/macro/model/macroChartModel.test.ts --run` -> 4 files passed, 60 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture harness 14 files passed, 74 tests passed.
- `cd web && npm run format:check` -> pass.
- `rg -n 'return explicit \\?\\? "ok"|`\\$\\{tenorYears\\}Y`' web/src/features/macro/model/macroChartModel.ts` -> no matches.

## 2026-06-17 Continuation — Rates Diagnostics Label Hard Cut

Red tests:

- `cd web && npm run test -- tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts --run` initially failed because policy, curve, and real-rate diagnostics still rendered with default labels after backend `label` was removed.
- `cd web && npm run test:architecture -- tests/architecture/macroModelHardCut.test.ts` initially failed because `macroRatesWorkbenchModel.ts` still contained the default diagnostics label fallback expressions.

Implementation notes:

- `buildPolicyDiagnostics(...)` now requires explicit backend `label`.
- `buildCurveDiagnostics(...)` now requires explicit backend `label`.
- `buildRealRateDiagnostics(...)` now requires explicit backend `label`.
- Missing top-level labels now remove the diagnostics block instead of generating frontend section copy.
- `web/tests/architecture/macroModelHardCut.test.ts` rejects the retired default-label expressions.

Green tests and checks:

- `cd web && npm run test -- tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts --run` -> 1 file passed, 18 tests passed.
- `cd web && npm run test:architecture -- tests/architecture/macroModelHardCut.test.ts` -> architecture harness 14 files passed, 74 tests passed.
- `cd web && npm run test -- tests/component/features/macro/MacroRatesWorkbench.test.tsx tests/component/features/macro/MacroModulePages.test.tsx tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts --run` -> 3 files passed, 78 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture harness 14 files passed, 74 tests passed.
- `cd web && npm run format:check` -> pass.
- `rg -n 'stringValue\\(diagnostics\\.label\\) \\?\\? "政策走廊诊断"|stringValue\\(diagnostics\\.label\\) \\?\\? "曲线诊断"|stringValue\\(diagnostics\\.label\\) \\?\\? "实际利率诊断"' web/src/features/macro/model/macroRatesWorkbenchModel.ts` -> no matches.
- `rg -n 'metric:\\$\\{index\\}|\\$\\{bucketKey\\}:\\$\\{index\\}|row:\\$\\{rowIndex\\}|row:\\$\\{index\\}|\\$\\{stable\\}:\\$\\{rowIndex\\}|titleByKey\\[conceptKey\\] \\?\\? \"资产\"' web/src/features/macro/model/macroModulePresentation.ts web/src/features/macro/model/macroTableColumns.ts web/src/features/macro/model/macroCorrelationModel.ts web/src/features/macro/ui/correlation/MacroCorrelationTables.tsx` -> no matches.

## 2026-06-17 Continuation — Rates Diagnostics Row Identity Hard Cut

Red tests:

- `cd web && npm run test -- tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts --run` initially failed because policy diagnostics, curve diagnostics, curve history, tenor comparison, and real-rate diagnostics still kept rows without backend `key` or `label` by manufacturing index-derived keys and labels such as `policy-row:${index}`, `curve-row:${index}`, `curve-history:${seriesIndex}`, `tenor:${index}`, `${groupKey}:${index}`, `政策读数 ${index + 1}`, `曲线 ${index + 1}`, `利差历史 ${seriesIndex + 1}`, `期限 ${index + 1}`, `实际利率读数 ${index + 1}`, and `点 ${pointIndex + 1}`.

Implementation notes:

- Policy, curve, tenor, and real-rate diagnostic rows now require backend `key` and `label`.
- Curve history series now require backend `key` and `label`.
- Curve history points require `observed_at` and use `seriesKey:observed_at` keys instead of point-index keys.
- `web/tests/architecture/macroModelHardCut.test.ts` now rejects the retired rates diagnostics identity/label fallback templates.

Green tests and checks:

- `cd web && npm run test -- tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts --run` -> 1 file passed, 11 tests passed.
- `cd web && npm run test -- tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts tests/component/features/macro/MacroRatesWorkbench.test.tsx --run` -> 2 files passed, 32 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture harness 14 files passed, 74 tests passed.
- `cd web && npm run format:check` -> pass.
- `rg -n "policy-row:\\$\\{index\\}|curve-row:\\$\\{index\\}|curve-history:\\$\\{seriesIndex\\}|tenor:\\$\\{index\\}|\\$\\{groupKey\\}:\\$\\{index\\}|政策读数 \\$\\{index \\+ 1\\}|曲线 \\$\\{index \\+ 1\\}|利差历史 \\$\\{seriesIndex \\+ 1\\}|期限 \\$\\{index \\+ 1\\}|实际利率读数 \\$\\{index \\+ 1\\}|点 \\$\\{pointIndex \\+ 1\\}" web/src/features/macro/model/macroRatesWorkbenchModel.ts` -> no matches.

## 2026-06-17 Continuation — Rates Facts Raw Concept Hard Cut

Red tests:

- `cd web && npm run test -- tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts --run` initially failed because `humanizeRatesConceptKey("rates:not_mapped")` still returned generated copy, facts without backend `concept_key` or `label` still rendered through label/fact-index/known-concept fallbacks, and rates explanatory text still allowed unknown concept ids to become generated words.

Implementation notes:

- `humanizeRatesConceptKey(...)` now returns `null` for concept ids not present in the explicit rates concept label map.
- `buildRatesFact(...)` now requires backend `concept_key`, explicit `label`, and displayable value.
- `missingPrimaryItems(...)` drops unknown missing concept ids instead of humanizing raw fragments.
- `sanitizePrimaryText(...)` still maps known concept ids to explicit labels but removes unknown concept ids.
- `web/tests/architecture/macroModelHardCut.test.ts` now rejects `fact:${index}` and raw `conceptKey.split(":")` humanization.

Green tests and checks:

- `cd web && npm run test -- tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts --run` -> 1 file passed, 14 tests passed.
- `cd web && npm run test -- tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts tests/component/features/macro/MacroRatesWorkbench.test.tsx --run` -> 2 files passed, 35 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture harness 14 files passed, 74 tests passed.
- `cd web && npm run format:check` -> pass.
- `rg -n 'fact:\\$\\{index\\}|conceptKey\\.split\\(\":\"\\)|humanizeRatesConceptKey\\(key\\)|stringValue\\(tile\\.short_label\\) \\?\\? humanizeRatesConceptKey' web/src/features/macro/model/macroRatesWorkbenchModel.ts` -> no matches.

## 2026-06-17 Continuation — Rates Gap Summary Hard Cut

Red tests:

- `cd web && npm run test -- tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts --run` initially failed because rates data-health gaps without backend `code` still rendered as `gap:${index}`, while gaps with raw codes but no labels still rendered generated text such as `rates NOT mapped GAP`.

Implementation notes:

- `gapSummaries(...)` now drops gaps without backend `code` or explicit `label`/`display_value`.
- `missingPrimaryItems(...)` now uses the same explicit gap-label contract instead of treating raw codes as display copy.
- `humanizeGapCode(...)` and the raw `code.split(/[:_]+/)` fallback were removed.
- `web/tests/architecture/macroModelHardCut.test.ts` now rejects `gap:${index}` and raw gap-code split fallback.

Green tests and checks:

- `cd web && npm run test -- tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts --run` -> 1 file passed, 15 tests passed.
- `cd web && npm run test -- tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts tests/component/features/macro/MacroRatesWorkbench.test.tsx --run` -> 2 files passed, 36 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture harness 14 files passed, 74 tests passed.
- `cd web && npm run format:check` -> pass.
- `cd web && npm run test:architecture -- tests/architecture/macroModelHardCut.test.ts` -> architecture harness 14 files passed, 74 tests passed.
- `rg -n 'gap:\\$\\{index\\}|code\\.split\\(/\\[:_\\]\\+/\\)|humanizeGapCode|gapDisplayLabel' web/src/features/macro/model/macroRatesWorkbenchModel.ts` -> no matches.

## 2026-06-17 Continuation — Provenance Source Row Contract Hard Cut

Red tests:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_build_macro_module_view_projects_v3_display_contract -q` initially failed because backend provenance rows still emitted `source` without `row_id` / `source_label`.
- `cd web && npm run test -- tests/component/features/macro/MacroDataTable.test.tsx --run` initially failed because `MacroSourceTable` still rendered rows missing backend row identity or `source_label` by inferring labels from `source`, `label`, or `name`.

Implementation notes:

- Backend `_observation_source_rows(...)` now emits `row_id` and `source_label` for provenance rows and removes the generic `source` display field.
- `MacroSourceTable` requires `row_id` and `source_label`; it no longer builds ids with `${source}:${index}` or infers labels from `label` / `source` / `name`.
- Rates source metadata summaries now read `source_label`.
- `macroFixture` provenance rows now use the new source row contract.
- `web/tests/architecture/macroModelHardCut.test.ts` now rejects the retired source-row identity and label fallback expressions.

Green tests and checks:

- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py::test_build_macro_module_view_projects_v3_display_contract -q` -> 1 passed.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run pytest tests/unit/domains/macro_intel/test_macro_module_views.py -q` -> 114 passed.
- `cd web && npm run test -- tests/component/features/macro/MacroDataTable.test.tsx --run` -> 1 file passed, 10 tests passed.
- `cd web && npm run test -- tests/component/features/macro/MacroDataTable.test.tsx tests/component/features/macro/MacroModulePages.test.tsx tests/unit/features/macro/model/macroRatesWorkbenchModel.test.ts tests/component/features/macro/MacroRatesWorkbench.test.tsx --run` -> 4 files passed, 81 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture harness 14 files passed, 74 tests passed.
- `cd web && npm run format:check` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py` -> pass.
- `UV_CACHE_DIR=/tmp/parallax-uv-cache uv run ruff format --check src/parallax/domains/macro_intel/services/macro_module_views.py tests/unit/domains/macro_intel/test_macro_module_views.py` -> 2 files already formatted.
- `rg -n '`\\$\\{source\\}:\\$\\{index\\}`|stringValue\\(row\\.label\\) \\?\\?|stringValue\\(row\\.source\\) \\?\\?|stringValue\\(row\\.name\\)|sourceRow\\([^)]*index|sourceRow\\(row, index\\)' web/src/features/macro/ui/tables/MacroSourceTable.tsx web/src/features/macro/model/macroRatesWorkbenchModel.ts src/parallax/domains/macro_intel/services/macro_module_views.py` -> no matches.

## 2026-06-17 Continuation — Chart Status And Placeholder Hard Cut

Red tests:

- `cd web && npm run test -- tests/unit/features/macro/model/macroChartModel.test.ts tests/component/features/macro/MacroMarketBoard.test.tsx --run` initially failed because chart status still rendered as `unknown`, missing chart ids still became `unknown_chart`, unlabeled chart rows still rendered placeholder labels, and the market board still rendered incomplete chart/table blocks.

Implementation notes:

- `MacroTimeSeriesModel.status` is now nullable, and `statusValue(...)` returns `null` when the backend omits status metadata.
- Time-series and yield-curve chart models require explicit chart ids instead of assigning `unknown_chart`.
- Chart series and heatmap rows require backend labels; unlabeled rows are omitted instead of receiving `未命名指标`.
- `MacroMarketBoard` now skips empty primary-chart/table blocks and only displays chart status labels when the backend provides status text.
- `web/tests/architecture/macroModelHardCut.test.ts` rejects the retired chart status fallback expressions.

Green tests and checks:

- `cd web && npm run test -- tests/unit/features/macro/model/macroChartModel.test.ts tests/component/features/macro/MacroCharts.test.tsx tests/component/features/macro/MacroMarketBoard.test.tsx tests/component/features/macro/MacroModulePages.test.tsx --run` -> 4 files passed, 55 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture harness 14 files passed, 74 tests passed.
- `cd web && npm run format:check` -> pass.
- `rg -n 'String\\(chart\\.status \\?\\? "unknown"\\)|stringValue\\(value\\) \\?\\? "unknown"|chart\\.status \\?\\? "unknown"' web/src/features/macro/model/macroChartModel.ts web/src/features/macro/ui/pages/MacroMarketBoard.tsx` -> no matches.

## 2026-06-17 Continuation — Asset Overview Placeholder Hard Cut

Red tests:

- `cd web && npm run test -- tests/unit/features/macro/model/macroAssetOverviewModel.test.ts --run` initially failed because `normalizeDailyBrief(...)` still manufactured `status: "unknown"` when backend status was missing.
- `cd web && npm run test:architecture -- tests/architecture/macroModelHardCut.test.ts` initially failed because asset overview still contained the retired daily-brief placeholders, row-id symbol splitting, and diagnostics `data-severity="unknown"` attributes.

Implementation notes:

- `normalizeDailyBrief(...)` now requires backend `headline` and `status` before returning a brief.
- Daily-brief blocks require explicit `stance`; missing stance no longer becomes `neutral`.
- Daily-brief data-quality summaries require explicit `status`; missing quality status no longer becomes `unknown`.
- Asset market rows no longer derive symbols from row-id suffixes such as `asset:dji`.
- Asset, workbench, and rates diagnostics gap lists omit the `data-severity` attribute when severity is absent instead of writing `unknown`.
- `web/tests/architecture/macroModelHardCut.test.ts` rejects the retired asset-overview placeholder expressions.

Green tests and checks:

- `cd web && npm run test -- tests/unit/features/macro/model/macroAssetOverviewModel.test.ts --run` -> 1 file passed, 3 tests passed.
- `cd web && npm run test:architecture -- tests/architecture/macroModelHardCut.test.ts` -> architecture harness 14 files passed, 74 tests passed.
- `cd web && npm run test -- tests/component/features/macro/MacroModulePages.test.tsx tests/component/features/macro/MacroRatesWorkbench.test.tsx tests/unit/features/macro/model/macroAssetOverviewModel.test.ts --run` -> 3 files passed, 59 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture harness 14 files passed, 74 tests passed.
- `cd web && npm run format:check` -> pass.
- `rg -n 'String\\(record\\.headline \\?\\? "今日判断暂不可用"\\)|String\\(record\\.status \\?\\? "unknown"\\)|String\\(record\\.stance \\?\\? "neutral"\\)|key\\.split\\(":"\\)\\.at\\(-1\\)|data-severity=\\{item\\.severity \\?\\? "unknown"\\}' web/src/features/macro` -> no matches.

## 2026-06-17 Continuation — Page Gap Raw-Code Label Hard Cut

Red tests:

- `cd web && npm run test -- tests/unit/features/macro/model/macroPageViewModel.test.ts --run` initially failed because raw gap strings still rendered labels such as `历史样本不足：60d`, and unlabeled stale gaps still manufactured freshness-alert item labels.
- `cd web && npm run test:architecture -- tests/architecture/macroModelHardCut.test.ts` initially failed because `macroPageViewModel.ts` still contained `gapCodeLabel(...)`, `GAP_CODE_TERMS`, raw code splitting, and generic stale item fallback copy.

Implementation notes:

- `gapLabel(...)` now returns only backend `display_value`, `label`, or `title`.
- Raw primitive gap strings and code-only gap objects now return `null`.
- `staleGapLabel(...)` no longer falls back to generic copy; freshness-alert items require explicit backend labels.
- Removed `gapCodeLabel(...)`, `gapCodeSubjectLabel(...)`, and `GAP_CODE_TERMS`.
- Updated `macroModulePresentation` expectations so code-only data-health gaps are dropped instead of receiving generated labels.

Green tests and checks:

- `cd web && npm run test -- tests/unit/features/macro/model/macroPageViewModel.test.ts --run` -> 1 file passed, 14 tests passed.
- `cd web && npm run test:architecture -- tests/architecture/macroModelHardCut.test.ts` -> architecture harness 14 files passed, 74 tests passed.
- `cd web && npm run test -- tests/unit/features/macro/model/macroPageViewModel.test.ts tests/unit/features/macro/model/macroModulePresentation.test.ts tests/component/features/macro/MacroModulePages.test.tsx tests/component/features/macro/MacroDataTable.test.tsx --run` -> 4 files passed, 68 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture harness 14 files passed, 74 tests passed.
- `cd web && npm run format:check` -> pass.
- `rg -n 'gapCodeLabel\\(|GAP_CODE_TERMS|最新宏观观测滞后|\\.split\\(/\\[:_\\]\\+/u\\)' web/src/features/macro` -> no matches.

## 2026-06-17 Continuation — Diagnostics Status Summary Hard Cut

Red tests:

- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx tests/component/features/macro/MacroRatesWorkbench.test.tsx --run` initially failed because workbench brief status exposed raw snapshot status, diagnostics exposed raw `summary_status`, asset diagnostics displayed raw `ok`, and rates diagnostics rendered `1 个来源` from source counts.
- `cd web && npm run test:architecture -- tests/architecture/macroModelHardCut.test.ts` initially failed because the retired raw-status/default-status/source-count fallback expressions were still present.

Implementation notes:

- `buildMacroWorkbenchBrief(...)` now uses `macroStatusLabel(...)` instead of raw snapshot `status`.
- `buildMacroWorkbenchDiagnostics(...)` now uses only backend `data_health.summary_label` for display status.
- `MacroDiagnosticsPanel` omits the status summary row when `statusLabel` is absent instead of rendering `正常`.
- `MacroAssetOverviewPage` omits the diagnostics status badge when `summary_label` is absent instead of rendering raw `summary_status`.
- `RatesDiagnosticsPanel` shows the source diagnostics section only when `view.diagnostics.sourceMeta` exists; it no longer manufactures source copy from row counts.
- `web/tests/architecture/macroModelHardCut.test.ts` rejects the retired fallback expressions.

Green tests and checks:

- `cd web && npm run test -- tests/unit/features/macro/model/macroWorkbenchModel.test.ts tests/component/features/macro/MacroModulePages.test.tsx tests/component/features/macro/MacroRatesWorkbench.test.tsx --run` -> 3 files passed, 100 tests passed.
- `cd web && npm run test:architecture -- tests/architecture/macroModelHardCut.test.ts` -> architecture harness 14 files passed, 74 tests passed.
- `cd web && npm run typecheck` -> pass.
- `cd web && npm run lint` -> ESLint passed; architecture harness 14 files passed, 74 tests passed.
- `cd web && npm run format:check` -> pass.
