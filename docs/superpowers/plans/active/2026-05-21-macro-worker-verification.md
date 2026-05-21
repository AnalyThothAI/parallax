# Macro Worker Verification

Date: 2026-05-21
Branch: `codex/macro-views-worker`

## Passing Checks

- Rebased onto current `main` (`9b93ed5c update web`) before the final verification pass.
- `uv run --no-sync ruff check .`
  - Passed: `All checks passed!`
- `uv run --no-sync mypy src/gmgn_twitter_intel/domains/macro_intel src/gmgn_twitter_intel/app/surfaces/api/routes_macro.py src/gmgn_twitter_intel/app/runtime/worker_factories/macro_intel.py`
  - Passed: `Success: no issues found in 10 source files`
- `uv run --no-sync python -m pytest tests/unit/domains/macro_intel/test_macro_regime_engine.py tests/unit/domains/macro_intel/test_macro_view_projection_worker.py tests/unit/test_api_macro_contract.py tests/unit/test_bootstrap_worker_runtime_wiring.py::test_worker_factory_wires_news_fetch_by_default tests/architecture/test_worker_inventory_contract.py tests/architecture/test_worker_runtime_contracts.py -q`
  - Passed: `73 passed in 10.17s`
- `npm test -- --run tests/component/features/macro/MacroPage.test.tsx tests/routes/macro.route.test.tsx`
  - Passed: `2 passed`, `3 tests passed`
- `npm run typecheck`
  - Passed
- `npm run lint`
  - Passed
- `npm run build`
  - Passed; Vite emitted the existing large chunk warning for `index-*.js`.
- `git diff --check`
  - Passed

## Baseline / Historical Failing Gates

- `uv run --no-sync ruff format --check .`
  - Failed on 52 pre-existing files after formatting this feature's touched Python files.
  - The remaining list does not include `macro_intel`, `/api/macro`, the macro worker factory, the macro worker registry entry, macro migration, or macro tests.
- `cd web && npm run format:check`
  - Failed on 9 pre-existing files:
    - `src/features/news/newsViewModel.ts`
    - `src/features/news/useNewsPage.ts`
    - `src/features/search/model/searchCase.ts`
    - `src/lib/api/client.ts`
    - `src/routes/ops.route.tsx`
    - `tests/fixtures/tokenCaseFixture.ts`
    - `tests/unit/lib/apiClient.news.test.ts`
    - `tests/unit/shared/model/narrativeDataGaps.test.ts`
    - `tests/unit/shared/model/tokenRadarCompactCase.test.ts`
- `uv run --no-sync mypy src`
  - Failed with 89 errors in 30 files. The failures are in existing Pulse, Narrative, News, Watchlist, CEX/CoinGlass, OpenAI integration, news-feed adapter, settings, and CLI modules.
  - The targeted macro files pass mypy separately.
- `uv run --no-sync python -m pytest tests/architecture/test_src_domain_architecture.py -q`
  - Failed with 4 known architecture boundary failures:
    - Pulse service imports `token_intel._constants` directly.
    - Narrative repositories/queries import service-layer modules.
    - Pulse service modules contain raw SQL outside repository/query boundaries.
    - OpenAI agent integration imports a Pulse service.
- `make check-all`
  - Failed at the Python format gate because of the 52 historical files above, before reaching later gates.

## Chain Coverage

- Worker chain: `MacroViewProjectionWorker` reads latest `macro_observations`, builds a deterministic snapshot through `build_macro_view_snapshot`, and writes `macro_view_snapshots`.
- API chain: `/api/macro` returns the latest snapshot or a stable missing-snapshot data-gap envelope.
- Frontend chain: `/macro` calls `/api/macro`, renders the regime header, panel scores, indicators, triggers, data gaps, and marks the Macro rail item active.
