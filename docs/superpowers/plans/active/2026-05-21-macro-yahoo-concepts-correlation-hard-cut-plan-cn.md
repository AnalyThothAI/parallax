# Macro Yahoo Concepts Correlation Hard Cut Plan

**Goal:** 将 macro 页面从 provider-bound series 升级为 concept-first 的宏观资产工作台：`macrodata-cli` 用 Yahoo/yfinance 补齐资产历史，gmgn 事实层按 canonical `concept_key` 投影，`/macro/assets/correlation` 展示真实滚动相关性。

**Hard-cut rules:**
- 不保留 Stooq fallback。
- 不保留旧 `series_key` UI fallback。
- 不在前端临时计算相关性。
- 不引入 OpenBB 运行依赖。
- 不添加兼容旧 snapshot 的双路径代码；投影版本直接升级到 `macro_regime_v3`。

## Task 1 - macrodata-cli Yahoo Provider

**Repository:** `/Users/qinghuan/Documents/code/macrodata-cli`

**Files:**
- `pyproject.toml`
- `uv.lock`
- `src/macrodata/providers/yahoo.py`
- `src/macrodata/app/runtime.py`
- `src/macrodata/catalog/entries.py`
- `src/macrodata/app/services.py`
- `tests/provider/test_yahoo_provider.py`
- `tests/unit/test_catalog.py`
- `tests/unit/test_bundles.py`
- `tests/unit/test_runtime.py`
- `tests/cli/test_bundle_commands.py`

**Requirements:**
- Add `yfinance` as a direct dependency.
- Add `YahooPriceProvider` with `provider_name = "yahoo"`.
- Implement `get_range(dataset, start, end)` and `get_latest(dataset)` using daily `Ticker.history(...)`.
- Use adjusted daily close as the canonical value. No intraday support.
- Emit `MacroObservation(series_key=f"yahoo:{dataset}", provider="yahoo", unit="price", frequency="daily", latency_class="daily")`.
- Add provenance with provider `yahoo`, upstream `Yahoo Finance`, and yfinance unofficial/personal-use license note.
- Replace macro-core Stooq asset proxies with Yahoo series:
  - `yahoo:SPY`
  - `yahoo:QQQ`
  - `yahoo:IWM`
  - `yahoo:TLT`
  - `yahoo:HYG`
  - `yahoo:LQD`
  - `yahoo:GLD`
  - `yahoo:USO`
  - `yahoo:DX-Y.NYB`
  - `yahoo:BTC-USD`
  - `yahoo:ETH-USD`
- Keep Stooq provider code only if other non-macro commands still reference it; remove it from macro-core.
- Tests must assert macro-core source chain contains `yahoo` and does not contain `stooq`.

**Verification:**
- `uv run pytest tests/provider/test_yahoo_provider.py tests/unit/test_catalog.py tests/unit/test_bundles.py tests/unit/test_runtime.py tests/cli/test_bundle_commands.py`
- `uv run ruff check .`
- `uv run mypy src`

## Task 2 - gmgn Concept-Key Facts And v3 Projection

**Repository:** `/Users/qinghuan/Documents/code/gmgn-twitter-intel`

**Files:**
- `src/gmgn_twitter_intel/platform/db/alembic/versions/<next>_macro_concept_key_hard_cut.py`
- `src/gmgn_twitter_intel/domains/macro_intel/_constants.py`
- `src/gmgn_twitter_intel/domains/macro_intel/repositories/macro_intel_repository.py`
- `src/gmgn_twitter_intel/domains/macro_intel/services/macrodata_bundle_importer.py`
- `src/gmgn_twitter_intel/domains/macro_intel/services/macro_feature_engine.py`
- `src/gmgn_twitter_intel/domains/macro_intel/services/macro_regime_engine.py`
- `src/gmgn_twitter_intel/domains/macro_intel/runtime/macro_view_projection_worker.py`
- `tests/unit/domains/macro_intel/`
- `tests/unit/test_api_macro_contract.py`
- `tests/unit/test_cli_macro_commands.py`

**Requirements:**
- Add `macro_observations.concept_key TEXT NOT NULL` and `source_priority INTEGER NOT NULL`.
- Add unique identity on `(concept_key, observed_at, source_name, series_key)`.
- Replace projection version with `macro_regime_v3`.
- Replace `MACRO_CORE_SERIES` with `MACRO_CORE_CONCEPTS`.
- Map provider series to canonical concepts at import time. Unknown macro-core series must fail import.
- Preserve raw provider `series_key` only as provenance/source metadata.
- Repository history reads must dedupe by `(concept_key, observed_at)` and select highest `source_priority`, then latest `ingested_at_ms`.
- Feature keys returned to UI must be concept keys, not provider keys.
- Existing regime logic must consume concept keys only.
- No fallback reads by old provider `series_key`.

**Required concept map:**
- `liquidity:fed_assets` <- `fred:WALCL`
- `liquidity:reserve_balances` <- `fred:WRBWFRBL`
- `liquidity:on_rrp` <- `fred:RRPONTSYD`
- `liquidity:sofr` <- `nyfed:SOFR`
- `liquidity:tga` <- `treasury_fiscal:operating_cash_balance`
- `rates:dgs2` <- `fred:DGS2`
- `rates:dgs5` <- `fred:DGS5`
- `rates:dgs10` <- `fred:DGS10`
- `rates:dgs30` <- `fred:DGS30`
- `rates:10y2y` <- `fred:T10Y2Y`
- `rates:10y3m` <- `fred:T10Y3M`
- `rates:real_10y` <- `fred:DFII10`
- `inflation:10y_breakeven` <- `fred:T10YIE`
- `inflation:5y5y_forward` <- `fred:T5YIFR`
- `fed:target_upper` <- `fred:DFEDTARU`
- `fed:target_lower` <- `fred:DFEDTARL`
- `fed:effr` <- `fred:EFFR`
- `fed:iorb` <- `fred:IORB`
- `credit:ig_oas` <- `fred:BAMLC0A0CM`
- `credit:hy_oas` <- `fred:BAMLH0A0HYM2`
- `vol:vix` <- `fred:VIXCLS`
- `asset:spx` <- `fred:SP500`
- `commodity:wti` <- `fred:DCOILWTICO`
- `fx:broad_dollar` <- `fred:DTWEXBGS`
- `asset:spy` <- `yahoo:SPY`
- `asset:qqq` <- `yahoo:QQQ`
- `asset:iwm` <- `yahoo:IWM`
- `asset:tlt` <- `yahoo:TLT`
- `asset:hyg` <- `yahoo:HYG`
- `asset:lqd` <- `yahoo:LQD`
- `asset:gld` <- `yahoo:GLD`
- `asset:uso` <- `yahoo:USO`
- `fx:dxy` <- `yahoo:DX-Y.NYB`
- `crypto:btc` <- `yahoo:BTC-USD`
- `crypto:eth` <- `yahoo:ETH-USD`
- `positioning:sp500_net_noncommercial` <- `cftc:financial_futures:sp500_net_noncommercial`

**Verification:**
- `uv run pytest tests/unit/domains/macro_intel tests/unit/test_api_macro_contract.py tests/unit/test_cli_macro_commands.py`
- `uv run ruff check src/gmgn_twitter_intel/domains/macro_intel tests/unit/domains/macro_intel tests/unit/test_api_macro_contract.py tests/unit/test_cli_macro_commands.py`
- `uv run mypy src/gmgn_twitter_intel/domains/macro_intel`

## Task 3 - Asset Correlation Projection And Route

**Repository:** `/Users/qinghuan/Documents/code/gmgn-twitter-intel`

**Files:**
- `src/gmgn_twitter_intel/platform/db/alembic/versions/<next>_macro_correlations_json.py`
- `src/gmgn_twitter_intel/domains/macro_intel/services/macro_correlation_engine.py`
- `src/gmgn_twitter_intel/domains/macro_intel/services/macro_regime_engine.py`
- `src/gmgn_twitter_intel/domains/macro_intel/repositories/macro_intel_repository.py`
- `src/gmgn_twitter_intel/app/surfaces/api/routes_macro.py`
- `web/src/lib/types/frontend-contracts.ts`
- `web/src/features/macro/MacroPage.tsx`
- `web/src/features/macro/macro.css`
- `web/tests/component/features/macro/MacroPage.test.tsx`
- `web/tests/routes/macro.route.test.tsx`
- `tests/unit/domains/macro_intel/test_macro_correlation_engine.py`
- `tests/unit/test_api_macro_contract.py`

**Requirements:**
- Add `macro_view_snapshots.correlations_json JSONB NOT NULL DEFAULT '{}'::jsonb`.
- Compute 30d and 90d rolling daily-return correlations from concept-key history.
- Correlation universe:
  - `asset:spy`
  - `asset:qqq`
  - `asset:iwm`
  - `asset:tlt`
  - `asset:hyg`
  - `asset:lqd`
  - `asset:gld`
  - `asset:uso`
  - `fx:dxy`
  - `crypto:btc`
  - `crypto:eth`
- Emit `sample_count`, `window`, `pairs`, and warning signals:
  - `stock_bond_positive_correlation`
  - `oil_equity_negative_correlation`
  - `crypto_equity_high_beta`
  - `dollar_risk_inverse`
- Add `/macro/assets/correlation` secondary page.
- Page must show heatmap, window switch, pair table, warnings, data gaps, source/sample counts.
- Do not compute correlation in React; React only renders `correlations_json`.
- If samples are insufficient, show explicit data gaps instead of placeholder heatmap.

**Verification:**
- `uv run pytest tests/unit/domains/macro_intel/test_macro_correlation_engine.py tests/unit/test_api_macro_contract.py`
- `cd web && npm test -- --run tests/component/features/macro/MacroPage.test.tsx tests/routes/macro.route.test.tsx`
- `cd web && npm run typecheck`
- `cd web && npm run lint`
- `cd web && npm run build`

## Subagent Execution Order

1. Implement Task 1 in `macrodata-cli`.
2. Review Task 1 for spec compliance and code quality.
3. Implement Task 2 in `gmgn-twitter-intel`.
4. Review Task 2 for spec compliance and code quality.
5. Implement Task 3 in `gmgn-twitter-intel`.
6. Review Task 3 for spec compliance and code quality.
7. Run end-to-end macro refresh:
   - generate `macrodata bundle history macro-core`;
   - import into gmgn;
   - run `gmgn-twitter-intel macro project-once`;
   - open `/macro/assets/correlation`.
8. Record final verification output in a verification doc before declaring done.
