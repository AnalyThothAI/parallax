# Plan — Macro Decision Console

**Status**: Draft
**Superseded by**: Not superseded
**Date**: 2026-06-16
**Owning spec**: `docs/sdd/features/active/2026-06-16-macro-decision-console/spec.md`
**Worktree**: `.worktrees/macro-decision-console`
**Branch**: `codex/macro-decision-console`
**Approved by**: Delegated goal from user on 2026-06-16
**Approved at**: 2026-06-16

## Pre-flight

- [ ] Create worktree: `git worktree add .worktrees/macro-decision-console -b codex/macro-decision-console main`.
- [ ] Verify worktree: `git worktree list`, `git status --short`, `git branch --show-current`.
- [ ] Run Parallax config diagnostic: `uv run parallax config`; record only redacted paths and booleans.
- [ ] Run macro status diagnostic: `uv run parallax macro status`; record counts, coverage, snapshot status, and missing concept labels.
- [ ] Run macrodata diagnostic in `/Users/qinghuan/Documents/code/macrodata-cli`: `uv run macrodata doctor`, `uv run macrodata bundle macro-core --asof 2026-06-16`.
- [ ] Baseline frontend gate: `cd web && npm run lint`, `cd web && npm run test:architecture`, `cd web && npm run typecheck`.
- [ ] Baseline Python macro gate: `uv run pytest tests/architecture/test_macro_no_compatibility_contract.py tests/unit/domains/macro_intel -q`.
- [ ] Baseline macrodata gate in `/Users/qinghuan/Documents/code/macrodata-cli`: `uv run pytest -q`, `uv run ruff check .`, `uv run mypy src tests`.

Known baseline findings from discovery:

- Parallax runtime uses `/Users/qinghuan/.parallax/config.yaml` and `/Users/qinghuan/.parallax/workers.yaml`; macrodata is enabled and FRED is configured through the `FINANCE_FRED_API_KEY` env name.
- `uv run parallax macro status` reports latest snapshot `partial`, history coverage `0.8425`, 20 concepts below minimum history, and projection lag `0`.
- Standalone macrodata-cli has `fred_api_key_configured=false`; `bundle macro-core` returned 67/128 available series and many FRED timeout errors through public CSV fallback.

## File-Level Edits

### `src/parallax/domains/macro_intel/services/macro_module_catalog.py`

- Lines 41-72: replace the broad 31-id `MACRO_MODULE_IDS` inventory with a retained allowlist only. Do not add a hidden/deferred tier.
- Lines 75-726: delete module configs for auctions, Fed statements, Fed speeches, volatility dashboard, CDS proxy, global dollar, subsurface funding, consumer, and crypto derivatives unless the implementation finds one is genuinely source-backed and decision-useful.
- Lines 88-95, 157-165, 281-282, 380-403, 536-555, 659-724: remove deleted routes from every `related_routes` list.
- Add tests in `tests/unit/domains/macro_intel/test_macro_module_catalog.py` asserting retained ids, deleted ids absent from the catalog, and no retained config links to deleted routes.

### `src/parallax/domains/macro_intel/services/macro_scenario_engine.py`

- Lines 1-220: add a deterministic decision-console shaper that uses existing `chain`, `panels`, `features`, `triggers`, and `data_gaps` to emit `top_changes`, `confirmations`, `contradictions`, `watch_triggers`, `invalidations`, `trade_map`, and `quality_blockers`.
- Keep only one current contract for new data. Do not add duplicate legacy field names.
- Add unit tests that fixture a tightening/funding-stress scenario and assert output has no empty top-change labels, no raw gap codes, and deterministic ordering.

### `src/parallax/domains/macro_intel/services/macro_regime_engine.py`

- Lines 1-120: thread the decision-console fields into `scenario_json` or a new nested `decision_console` section inside `scenario_json`.
- Lines 121-180: ensure `scorecard_json` keeps coverage and gap counts needed by the console.
- Add a unit test for `build_macro_view_snapshot(...)` asserting `scenario_json.decision_console` exists for partial snapshots and includes data-health blockers.

### `src/parallax/domains/macro_intel/services/macro_module_views.py`

- Lines 1-220: delete proxy-only view construction for removed module ids. The view builder should only know retained module ids.
- Ensure removed ids reach the same not-found path as unknown ids; do not add a special unavailable/deferred module view.
- Add tests asserting `rates/auctions`, `fed/statements`, `volatility/dashboard`, and `credit/cds` are not recognized module views.

### `src/parallax/app/surfaces/api/routes_macro.py`

- Locate the module route builder and ensure deleted module ids return ordinary not-found behavior, matching unknown ids.
- Ensure `/api/macro` includes the decision-console block from the persisted snapshot.
- Add API tests for `/api/macro` decision-console payload and deleted module ids returning not found.

### `web/src/features/macro/model/macroNavigationTree.ts`

- Lines 19-330: reduce public navigation to primary source-backed routes:
  - Keep: overview, assets, assets/equities, assets/bonds, assets/commodities, assets/fx, assets/crypto, assets/correlation, rates/fed-funds, rates/yield-curve, rates/real-rates, rates/expectations, liquidity/transmission-chain, liquidity/fed-balance-sheet, liquidity/operations, liquidity/rrp-tga, liquidity/reserves, economy/gdp, economy/employment, economy/inflation, volatility/vix, credit/stress.
  - Delete: assets/crypto-derivatives, rates/auctions, fed/statements, fed/speeches, liquidity/global-dollar, liquidity/subsurface, economy/consumer, volatility/dashboard, credit/cds.
- Remove hidden-label machinery from `web/src/features/macro/model/macroPageRegistry.ts` when it only exists to preserve deleted pages.
- Update architecture tests that assert route descriptors and page registry behavior.

### `web/src/features/macro/ui/pages/MacroOverviewModulePage.tsx`

- Replace the current overview composition with a decision-console reading order:
  1. Macro State strip: regime, confidence, as-of, coverage.
  2. Top Changes: three highest-impact source-backed changes.
  3. Confirm / Diverge: confirmations and contradictions.
  4. Trade Map: expression, time window, invalidations.
  5. Watch Triggers: next 24/72h or deterministic watch triggers.
  6. Data Quality Watch: blockers and source health.
- Keep existing `MacroMarketBoard`, `MacroInsightBrief`, and `MacroDiagnosticsPanel` primitives when they fit; do not create a new global CSS bucket.
- Add component tests to assert the order above and absence of raw gap codes.

### `web/src/features/macro/ui/pages/MacroModulePageRenderer.tsx`

- Remove any route branches that render deleted module ids.
- Ensure deleted routes are not reachable through the macro page registry, route fixtures, or module renderer.

### `web/src/features/macro/ui/pages/macroPages.css` and local macro CSS files

- Keep styles in `web/src/features/macro/ui/pages/macroPages.css` or adjacent owner CSS.
- Add compact console layout classes only under the macro namespace.
- Verify no retired global CSS files or shared UI internals are restyled.

### External macrodata-cli files

- In `/Users/qinghuan/Documents/code/macrodata-cli/src/macrodata/providers/fred.py`: keep API-key mode as primary, add redacted source-mode metadata, and distinguish public CSV fallback timeout from API failure.
- In `/Users/qinghuan/Documents/code/macrodata-cli/src/macrodata/app/services.py`: split macro-core diagnostics by provider/source mode while preserving the macro-core bundle name.
- In `/Users/qinghuan/Documents/code/macrodata-cli/src/macrodata/core/models.py`: make a single current diagnostics contract if typed support is needed; do not keep parallel legacy diagnostic fields.
- In `/Users/qinghuan/Documents/code/macrodata-cli/README.md` and reference docs: document provider diagnostics and required FRED API-key behavior.

### Documentation

- Update `docs/ARCHITECTURE.md` and `src/parallax/domains/macro_intel/ARCHITECTURE.md` if API/read-model semantics change.
- Update `docs/FRONTEND.md` only if route deletion/frontend ownership rules change.
- Append source backlog to `docs/TECH_DEBT.md` only for items not implemented in this feature.

## Data-Source Gap Backlog

| Domain | Gap | Public candidate | Paid candidate | Priority | Product impact |
|--------|-----|------------------|----------------|----------|----------------|
| Rates | Treasury auction calendar/results, bid-to-cover, tail, indirect/direct demand | TreasuryDirect auction XML/CSV, FiscalData where available | Bloomberg/Refinitiv | P1 | Rebuilds `rates/auctions` as a real page later. |
| Rates | Fed funds futures / meeting probabilities | CME public pages may not be stable for automated use; evaluate legal/technical path | CME DataMine, Bloomberg WIRP | P1 | Makes `rates/expectations` more than a short-rate proxy. |
| Fed | FOMC calendar, statements, minutes, speeches | federalreserve.gov calendars, press releases, speeches feeds | Bloomberg ECO/Fedspeak | P1 | Rebuilds Fed pages and supports catalysts. |
| Liquidity | Cross-currency basis and global dollar funding | BIS/FRB/H.4.1 where public, FRED limited proxies | Bloomberg/Refinitiv | P2 | Rebuilds global dollar page. |
| Liquidity | Intraday repo pressure and volumes | NY Fed SOFR percentiles/volumes if endpoint supports it | DTCC, Bloomberg | P2 | Rebuilds subsurface page. |
| Volatility | VIX futures curve, VXST/VIX/VXV/VXMT, VVIX, skew | Cboe CSV/download endpoints if license permits | Cboe DataShop, Bloomberg | P1 | Rebuilds vol dashboard. |
| Volatility | MOVE index | Check public ICE/BofA redistribution constraints; likely not safely public | ICE/Bloomberg | P2 | Better rates-vol confirmation. |
| Credit | SLOOS lending standards/demand | FRED SLOOS series | Haver/Bloomberg | P1 | Makes credit stress richer and source-backed. |
| Credit | Delinquency/charge-off/loan quality | FRED charge-off/delinquency series | Haver/Bloomberg | P1 | Detects late-cycle credit damage. |
| Credit | ETF premium/discount and TRACE liquidity | iShares/SPDR public ETF pages, FINRA TRACE aggregate files | Bloomberg/TRACE licensed | P2 | Adds market-liquidity confirmation. |
| Assets | Breadth, GEX, ETF flows | Nasdaq/NYSE breadth where public, OCC/Cboe if usable, ETF issuer flows | SpotGamma, Bloomberg | P2 | Improves asset confirmation and options gaps. |
| Economy | Release calendar and nowcast | BLS/BEA/FRED release tables, Atlanta Fed GDPNow | Bloomberg ECO | P1 | Adds catalysts and 24/72h calendar. |

## PR Breakdown

1. **PR 1 — Macro hard deletion and route allowlist**: module catalog cleanup, frontend navigation cleanup, deleted-route not-found tests.
2. **PR 2 — Decision console read model and overview UI**: scenario decision fields, `/api/macro` payload, overview layout, component tests.
3. **PR 3 — macrodata FRED diagnostics and bundle resilience**: FRED source-mode diagnostics, bundle coverage summaries, macrodata tests and docs, Parallax importer update if the diagnostics contract changes.
4. **PR 4 — Source backlog docs and operator verification**: architecture/doc updates, live macro status verification, SDD verification.

## Analyze Gate

| Check | Result |
|-------|--------|
| Spec goals map to file-level edits. | Pass: G1 maps to scenario/API/overview edits; G2 maps to catalog/API/frontend hard deletion; G3 maps to macrodata FRED/bundle edits; G4 maps to source backlog docs. |
| Plan preserves canonical architecture boundaries. | Pass: provider IO stays in macrodata/macro_sync; API and frontend read persisted views; no UI scoring is introduced. |
| Compatibility code or old files are not retained. | Pass: weak macro routes are deleted rather than hidden, deferred, or direct-link supported. |
| Parallel touch/conflict sets are explicit. | Pass: tasks split macrodata provider, Parallax domain/API, frontend route/UI, and docs with named conflict sets. |

## Rollout Order

1. Merge hard route deletion so the product stops advertising weak pages.
2. Merge decision-console payload and `/macro` overview UI.
3. Merge macrodata FRED/bundle diagnostics.
4. Run live `uv run parallax macro sync --bundle macro-core --start <date> --end <date>` only if operator explicitly wants a runtime refresh.
5. Verify `/macro` and retained primary child routes in desktop and mobile browser sessions.

## Rollback

1. Revert PR 1 to restore the previous route inventory. No compatibility branch remains in the shipped code.
2. Revert scenario/API decision-console fields.
3. Revert frontend overview layout changes.
4. Revert macrodata diagnostics changes and any matching Parallax importer update.
5. No destructive data migration is planned. If a migration becomes necessary, add a separate rollback section before implementation.

## Acceptance test commands

- AC1: `cd web && npm run test -- web/tests/component/features/macro/MacroModulePages.test.tsx -t "renders overview decision console" --run`
- AC2: `cd web && npm run test:architecture`
- AC3: `cd web && npm run test -- web/tests/routes/macro.route.test.tsx -t "removed macro routes are not registered" --run`
- AC4: `cd /Users/qinghuan/Documents/code/macrodata-cli && uv run pytest tests/provider/test_fred_provider.py tests/unit/test_bundles.py -q`
- AC5: `uv run parallax macro status`
- AC6: `make check-all`

## Verification

Verification evidence lives in `docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md`. The verification artifact must be filled before the feature directory moves to `completed/`.
