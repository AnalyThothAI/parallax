# Spec — Macro Decision Console

**Status**: In progress
**Superseded by**: Not superseded
**Date**: 2026-06-16
**Owner**: Codex
**Approved by**: Delegated goal from user on 2026-06-16
**Approved at**: 2026-06-16
**Related**: `docs/sdd/features/active/2026-06-16-macro-decision-console/plan.md`

## Background

Macro Intel is already a PostgreSQL-first read-model lane. Normal freshness is owned by macro sync, which runs the packaged macrodata-cli history bundle outside database transactions and persists normalized observations as macro observations; API routes and frontend pages must not call external providers directly (`src/parallax/domains/macro_intel/ARCHITECTURE.md:3`, `src/parallax/domains/macro_intel/ARCHITECTURE.md:24`). The public projection is macro regime v4, and module pages consume macro module view v3 fields for module read, evidence, transmission, data health, provenance, and related routes instead of recomputing conclusions in the UI (`src/parallax/domains/macro_intel/ARCHITECTURE.md:121`, `src/parallax/domains/macro_intel/ARCHITECTURE.md:152`, `src/parallax/domains/macro_intel/ARCHITECTURE.md:162`).

The baseline route audit found proxy-only, gap-only, or redundant pages: auctions, rate expectations, Fed statements, Fed speeches, volatility dashboard, CDS proxy, global dollar, subsurface funding, consumer, crypto derivatives, the duplicate bank-reserves liquidity page, the generic liquidity transmission page, and the generic public-operations liquidity page. The hard-deletion slice now narrows the catalog to retained source-backed ids and sends deleted ids through ordinary route-error behavior, with frontend tests asserting those routes are not kept as hidden direct routes, unsupported macro panels, deferred modules, or compatibility shells (`src/parallax/domains/macro_intel/services/macro_module_catalog.py:41`, `tests/unit/domains/macro_intel/test_macro_module_catalog.py:39`, `tests/unit/domains/macro_intel/test_macro_module_catalog.py:61`, `web/tests/unit/features/macro/model/macroPageRegistry.test.ts:20`).

The macrodata bundle baseline covered 128 provider series across liquidity, rates, economy, volatility, credit, assets, and CFTC positioning. This feature expands the current numeric provider/concept set by adding FRED SLOOS, loan-quality credit series, average hourly earnings, the Yahoo VIXM mid-term VIX futures ETF proxy, the Yahoo ^MOVE rates-volatility proxy, NY Fed repo/unsecured funding depth, GDPNow, official Cboe VIX1D/VIX9D/VVIX/SKEW volatility indexes, and a separate OKX/Deribit derivatives bundle for crypto OI/funding/basis/DVOL evidence (`src/parallax/domains/macro_intel/_constants.py:11`, `src/parallax/domains/macro_intel/_constants.py:149`). Parallax runtime reports the operator config at /Users/qinghuan/.parallax/config.yaml, workers config at /Users/qinghuan/.parallax/workers.yaml, macrodata enabled, and FRED configured through the FINANCE_FRED_API_KEY env name. The initial live macro status on 2026-06-16 reported 63,407 observations, 128 concepts, no projection lag, latest snapshot status partial, history coverage 0.8425, and 20 concepts below minimum history; after the latest VIX1D refresh recorded in verification, macro status reports 83,483 observations, 174 concepts, required history coverage 141/141, history-ready true, snapshot status ready, projection lag 0, and no concepts below minimum history (`docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md:17`, `docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md:946`, `docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md:1719`). The OKX/Deribit continuation is now packaged as macrodata-cli `0.1.22` and pinned in Parallax at Git rev `dd86aa8bcd234e8fb427ba9d058e9b478e2a0e6c`, with both fetch and history bundle surfaces exposed; verification records the package evidence and the remaining current-session network/Postgres live-import constraint (`docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md:2513`).

The standalone macrodata-cli checkout has no FRED_API_KEY configured. Running uv run macrodata bundle macro-core --asof 2026-06-16 in that checkout returned only 67 available series out of 128 and marked the bundle partial because many FRED public CSV requests timed out. The external FRED provider currently switches to public CSV when no API key exists and uses a per-request HTTP client with the same timeout for every FRED series (`docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md:19`).

External benchmark: timsun.net presents US macro as a decision console, not only as indicator pages. Its home page surfaces Macro State, a Trade Map, data-quality watch, the three most important changes, confirmation/divergence, liquidity pressure, future catalysts, and watchlist triggers. Its first-level sections for assets, rates, liquidity, volatility, and credit each reduce data into daily interpretation, source/as-of evidence, and validation triggers. Its trade-map page adds a five-asset radar (`NDX`, `BTC`, `GOLD`, `SPX`, `TLT`), deployed-capital/P&L framing, current actions, risk temperature, historical trust, holding-period review, and exit/risk events. Its yield-curve page compares curve shape, 2s10s/3m10s/5s30s, current/1w/1m/3m shifts, nominal/real/breakeven tenors, trade implications, and invalidation language. The product gap is therefore not just missing series; the larger gap is failure to compress cross-asset facts into a usable decision chain and then prove that chain historically (https://timsun.net/, https://timsun.net/trade-map, https://timsun.net/rates/yield-curve).

## Problem

The current macro product is too broad for its evidence base. It exposes many route names and related links that imply coverage parity with a macro terminal, while important pages remain proxy-only or gap-only. Users cannot quickly answer the first-order question: what changed in the macro chain today, which assets confirm or diverge, what invalidates the read, and which data quality gaps make the read unsafe.

## Clarifications

| Question | Answer | Approved by | Approved at |
|----------|--------|-------------|-------------|
| Should this work optimize for timsun.net-like decision usefulness rather than page-count parity? | Yes. The user explicitly asked to align with timsun.net and first-principles usability. | Delegated goal | 2026-06-16 |
| Should weak route surfaces be hidden/deferred or removed? | Removed. The user explicitly clarified: do not hide or take pages offline while preserving compatibility; completely clean unnecessary surfaces and do not keep compatibility code. | Delegated goal | 2026-06-16 |
| Should this first SDD record implement every missing macro source? | No. This record makes the product usable by pruning and decision-console shaping, then adds the smallest high-leverage data source improvements. Larger provider expansion gets successor records. | Codex scope decision | 2026-06-16 |

## Requirement Checklist

| Requirement | Quality gate |
|-------------|--------------|
| Align first screen to timsun.net decision-console logic. | `/macro` shows macro state, top changes, confirmations/divergences, data quality, catalysts/watch triggers, and a compact trade map from persisted read models. |
| Start with hard subtraction. | Proxy-only pages are deleted from module catalog, frontend route descriptors, related routes, fixtures, tests, and module rendering; old URLs use ordinary not-found behavior with no compatibility shim. |
| Preserve Kappa/CQRS boundaries. | No frontend provider calls; no UI-side macro scoring; API reads persisted facts/read models only. |
| Improve macrodata reliability for current bundle coverage. | Standalone `macrodata bundle macro-core` records a clear provider-mode diagnostic and does not let FRED public CSV timeouts dominate the whole decision console when API-key mode is available. |
| Research data-source gaps. | Plan records missing data sources by domain, public/paid status, priority, and target concept/page impact. |

## First Principles

1. Facts first, decisions second. Macro truth is `macro_observations`, and product state is deterministic read models; provider frames or UI heuristics are not product truth (`src/parallax/domains/macro_intel/ARCHITECTURE.md:10`).
2. A page is only useful if it answers a decision question. A route that only displays a proxy chart plus future gap labels should be removed from the product surface until it can contribute confirmation, contradiction, trigger, or data-quality evidence.
3. Data quality is part of the product, not a footer. Stale, partial, insufficient-history, and provider-error states must be shown near the decision they weaken.
4. No compatibility shells. Removed macro surfaces should not survive as hidden configs, direct-link pages, fallback branches, or duplicate old field names.

## Goals

- G1. `/macro` becomes a usable daily macro decision console: a user can identify current regime, confidence, top changes, confirmations/divergences, invalidations, watch triggers, and data-health blockers without opening child pages.
- G2. Public macro surface is reduced to source-backed modules only: Overview, Assets, Rates/Fed Funds, Rates/Yield Curve, Rates/Real Rates, Liquidity/Fed Balance Sheet, Liquidity/RRP-TGA, Volatility/VIX, Credit/Stress, and Economy/Inflation/Employment/GDP. Removed modules no longer exist as supported module ids.
- G3. macrodata-cli clearly separates API-key FRED mode from public CSV fallback and gives Parallax enough source-health evidence to explain FRED coverage degradation without masking it behind a generic partial state.
- G4. The data-source gap backlog is explicit and prioritized for assets, rates, Fed, liquidity, economy, volatility, and credit.

## Non-goals

- N1. This feature does not add paid Bloomberg, Refinitiv, Markit, Haver, CME, or ICE direct feeds.
- N2. This feature does not add a new PostgreSQL worker or table unless implementation discovers an unavoidable contract gap.
- N3. This feature does not change crypto Token Radar, News, Pulse, or Watchlist products except where macro links point into them.
- N4. This feature does not produce automated trade advice or order execution. Trade map remains explanatory and source-backed.

## Target architecture

Macro remains a single facts-to-read-model lane. macrodata-cli provides public macro observations and source-health metadata. Parallax persists those observations, projects a compact decision snapshot, and exposes `/api/macro` plus `/api/macro/modules/{module_id}` for retained modules only. The frontend renders the persisted decision snapshot and retained module views with no local scoring.

The target product has three layers:

- Decision Console: `/macro` summarizes regime, confidence, top changes, confirmations/divergences, data health, watch triggers, invalidations, and a compact expression map.
- Evidence Terminals: a smaller set of child pages shows source-backed detail for assets, rates, liquidity, volatility, credit, and economy.
- Research Backlog: unavailable domains such as Fed text delta scoring, BLS/BEA actual-vs-consensus and revision history, VIX futures curve and longer-tenor term structure, ETF premium/discount, TRACE, cross-currency basis, Fed funds futures, Treasury auction tail, remaining OFR/STFM funding distributions, and licensed ICE/Bloomberg MOVE or intraday redistribution are documented as source gaps. They have no runtime route, static module gap, future-integration warning, or frontend proxy-page branch until implemented. All implemented macro-core concepts are now visible in at least one retained module page. Existing nominal Treasury, TIPS, and breakeven curves are folded into `rates/yield-curve` and `rates/real-rates`, and missing implemented curve/real-rate depth groups now appear as `module_reference` gaps on those retained pages; PCE, core PCE, GDP deflator, MICH, and market inflation expectations are folded into `economy/inflation`, and missing implemented inflation-depth groups now appear as `module_reference` gaps on that retained page; SLOOS, loan-quality series, rating-ladder OAS, and public financial-condition indexes are now implemented as `credit/stress` evidence, and missing implemented credit-depth groups now appear as `module_reference` gaps on that retained page; PCE, real PCE, saving rate, UMich sentiment, nominal GDP, industrial production, and housing starts are folded into `economy/gdp` rather than reopening `economy/consumer`, and missing implemented growth-depth groups now appear as `module_reference` gaps on that retained page; JOLTS, average hourly earnings, and participation are implemented as `economy/employment` evidence, and missing implemented labor-depth groups now appear as `module_reference` gaps on that retained page; public equity, bond, commodity, and FX proxies are folded into retained asset pages, and missing implemented asset-depth groups now appear as `module_reference` gaps on retained asset pages; OKX/Deribit crypto derivatives are folded into retained `assets/crypto` table evidence and crypto asset-class diagnostics through `crypto-derivatives-core` rather than reopening `assets/crypto-derivatives`; VIXM, MOVE via `yahoo:^MOVE`, cross-asset volatility indexes, and official Cboe VIX1D/VIX9D/VVIX/SKEW are implemented as `volatility/vix` evidence, not as a replacement for a real CFE futures curve or licensed ICE terminal feed, and missing implemented VIX depth groups now appear as `module_reference` gaps on that retained page; NY Fed BGCR/TGCR plus SOFR/BGCR/TGCR underlying volumes are folded into retained `liquidity/rrp-tga` as repo-depth evidence rather than restoring `liquidity/subsurface`, and missing implemented liquidity-depth groups now appear as `module_reference` gaps on that retained page; NY Fed EFFR/OBFR plus EFFR/OBFR underlying volumes are folded into retained `rates/fed-funds` as unsecured-funding evidence rather than restoring rate-expectations, Fed text, or subsurface routes, and missing implemented policy-corridor depth groups now appear as `module_reference` gaps on that retained page; macrodata-cli now exposes a separate `macro-calendar-core` bundle for official Fed/BEA/BLS next-event catalysts without polluting Parallax numeric `macro-core` regime history; macrodata-cli now exposes a separate `treasury-auction-core` bundle for official Treasury 2Y/10Y/30Y tentative auction calendars plus completed auction result events that Parallax renders as overview catalysts without restoring the deleted `rates/auctions` route; and macrodata-cli now exposes `fed-text-core` for official Federal Reserve statement, minutes, press-release, and speech documents that Parallax renders as overview text catalysts without restoring deleted Fed text routes.

## Conceptual Data Flow

```text
macrodata public providers
  -> macrodata bundle history macro-core
  -> macro_observations
  -> macro_observation_series_rows
  -> macro_regime_v4 snapshot
  -> macro_daily_briefs assets_today
  -> /api/macro and retained /api/macro/modules/{module_id}
  -> web /macro decision console and selected evidence pages
```

The changed arrows are:

- macrodata provider fetch now emits clearer source-mode and fallback diagnostics.
- macro_regime_v4 scenario/read model gains decision-console-ready sections if the existing persisted fields are insufficient.
- web /macro stops treating every historical module id as a valid product page.

## Core Models

- MacroDecisionConsole: current regime, confidence, as-of, top changes, confirmations, divergences, catalysts/watch triggers, invalidations, trade map, and data health blockers derived from `scenario_json`, `features_json`, `chain_json`, `scorecard_json`, and `data_gaps_json`.
- MacroSupportedRouteSet: the exact retained module ids that can be rendered by API and frontend. It is an allowlist, not a tier system.
- MacroRemovedSurface: a documentation/test concept for routes deleted from product code. Removed surfaces can appear in source-gap docs and tests, but not in runtime registries.
- MacroSourceGap: domain, missing source, public or paid availability, concept impact, target product surface, priority, and acceptance signal.

## Interface Contracts

- `/api/macro`: continues to return deterministic macro overview state. It may add a decision-console block if current persisted sections are not enough; it must not keep duplicate old fields for compatibility.
- `/api/macro/modules/{module_id}`: retained modules return `macro_module_view_v3`. Deleted module ids behave like unknown module ids through the ordinary not-found route path; no hidden-supported or deferred view is added.
- `macrodata bundle macro-core`: may update the result envelope for provider source-health metadata. If the envelope changes, Parallax consumers and docs are updated in the same work; no long-lived legacy duplicate fields are kept.
- `macrodata bundle fetch macro-calendar-core`: emits official future-catalyst observations for FOMC, GDP, PCE/Personal Income and Outlays, CPI, Employment Situation, and PPI. Calendar observations use event date as `observed_at`, `days_until` as value, and source/event/time details in provenance; BLS observations also preserve the official reference period. Parallax imports these observations as `event:*` concepts for the overview decision console without expanding numeric `MACRO_CORE_CONCEPTS`, without restoring a calendar page, and without fabricating actual-vs-consensus or surprise data.
- `macrodata bundle fetch treasury-auction-core`: emits official U.S. Treasury tentative auction-calendar observations for the next nominal 2Y/10Y/30Y auctions plus FiscalData completed-auction result observations for 2Y/10Y/30Y high yield, bid-to-cover, and indirect bidder accepted percentage. Calendar observations use auction date as `observed_at`, `days_until` as value, and announcement/settlement/reopening metadata in provenance; result observations use auction date as `observed_at`, FiscalData record date as `source_ts`, and CUSIP/issue/accepted/tendered metadata in provenance. Auction tail is not calculated because no when-issued yield source is implemented. Parallax imports these observations as `event:*` concepts for the overview decision console without restoring the deleted `rates/auctions` route or rebuilding numeric regime snapshots for event-only changes.
- `macrodata bundle fetch fed-text-core`: emits official Federal Reserve text observations for latest FOMC statement, minutes, monetary-policy press release, and speech documents. Document observations keep the official title, source URL, and timestamp in provenance; Parallax stores same-day documents under stable URL-derived series keys so multiple speeches on one date do not collide. These observations are `event:*` catalysts only and do not restore `fed/statements` or `fed/speeches`.
- `macrodata bundle fetch crypto-derivatives-core`: emits public OKX BTC/ETH perpetual open interest, funding, and basis observations plus Deribit BTC/ETH perpetual open interest, 8h funding, basis, and volatility-index observations. Parallax maps these numeric observations to `crypto_derivatives:*` concepts, marks them optional for long-history readiness, schedules the bundle through `macro_sync`, and renders the rows inside retained `assets/crypto` evidence without restoring `assets/crypto-derivatives`.
- `macrodata bundle history macro-calendar-core`, `macrodata bundle history treasury-auction-core`, and `macrodata bundle history fed-text-core`: expose event bundles through the same bounded history-envelope shape used by Parallax `macro_sync`. Empty event-history windows must report `unavailable` / `no_observations`, not `ok`.
- `workers.macro_sync.bundle_names`: the formal Parallax runtime setting for default macrodata sync cadence. It replaces the old single `bundle_name` setting and defaults to `macro-core`, `macro-calendar-core`, `treasury-auction-core`, `fed-text-core`, and `crypto-derivatives-core`.
- Web `/macro`: renders only backend-provided macro decisions, data health, charts, and tables for retained modules.

## Acceptance criteria

- AC1. WHEN a user hard-loads `/macro` THEN the system SHALL show current macro state, confidence, top changes, confirmation/divergence, watch triggers, invalidations, trade map, and data health without requiring a child route.
- AC2. WHEN a user opens macro navigation THEN the system SHALL show only source-backed primary routes and SHALL not include auctions, rate expectations, Fed statements, Fed speeches, volatility dashboard, CDS proxy, global dollar, subsurface funding, consumer, crypto derivatives, the duplicate bank-reserves page, the generic liquidity transmission page, the generic public-operations liquidity page, or unavailable-source backlog warnings in any navigation, related-route list, fixture, runtime module gap, or module catalog.
- AC3. WHEN a deleted macro route is opened directly THEN the system SHALL use the ordinary not-found behavior and SHALL not render a legacy, hidden, deferred, or compatibility module shell.
- AC4. WHEN FRED public CSV is unavailable or timed out in standalone macrodata-cli THEN `bundle macro-core` SHALL return source-health diagnostics that identify FRED fallback mode and affected series without dropping available NY Fed, Treasury, Yahoo, and CFTC observations.
- AC5. WHEN Parallax runtime has `FINANCE_FRED_API_KEY` configured THEN macro status SHALL report FRED configured through a redacted boolean and macrodata bundle availability without exposing the key.
- AC6. WHEN the implementation is verified THEN frontend lint, architecture tests, typecheck, targeted macro component tests, macro Python tests, and macrodata-cli tests SHALL pass or list a concrete baseline blocker.
- AC7. WHEN `macro-calendar-core`, `treasury-auction-core`, or `fed-text-core` observations are imported THEN Parallax SHALL keep them out of numeric macro-core scoring, refresh them as event facts, and render source-backed `module_read.market_event_flow` in the overview without restoring deleted proxy pages or keeping duplicated decision-console event sections.
- AC8. WHEN `macro_sync` enqueues due work THEN it SHALL schedule every configured `bundle_names` entry through `macro_sync_windows`, and `macro status` SHALL report stale installed `macrodata-cli` packages that do not expose the configured event or crypto-derivatives bundles.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Removing historical URLs breaks bookmarks for power users. | Medium | Accepted by product direction; tests assert hard deletion so the break is explicit instead of accidental. |
| Decision console duplicates existing module logic. | High | Build from persisted `scenario_json`, `chain_json`, `features_json`, `scorecard_json`, and `data_health`; do not compute scores in frontend. |
| FRED public CSV is slow enough to block bundles. | High | Prefer API-key mode in runtime, add source-mode diagnostics, tune bounded timeout/retry/concurrency, and keep partial coverage honest. |
| Data-source backlog expands beyond one feature. | Medium | Record source gaps and split provider additions into successor SDD records. |
| UI changes violate frontend CSS ownership harness. | Medium | Keep CSS under `web/src/features/macro/ui/...`, run `npm run lint`, `npm run test:architecture`, and `npm run typecheck`. |

## Evolution Path

After this feature, successor records should add coverage in priority order: trade-map reliability/backtest from Parallax snapshots and asset histories; unrestricted live sync/projection verification for `crypto-derivatives-core`; FOMC statements/minutes/speeches from official Fed pages and RSS; Fed funds probability data from an approved CME/FedWatch or equivalent legal source before rebuilding `rates/expectations`; VIX futures curve, VXST/VXV/VXMT, realized-volatility, volume/OI, and options-surface evidence from approved Cboe/public or licensed feeds; deeper crypto derivatives stale-source checks, normalized history, and richer term/expiry structure after the retained `assets/crypto` derivative diagnostic slice; OCC/Cboe/OPRA options OI and GEX inputs; Treasury auction calendar/announcement/tail when a when-issued yield source exists; BIS/Bloomberg/Refinitiv global-dollar/cross-currency basis; OFR/STFM funding percentiles and unsecured funding depth beyond the first NY Fed repo-depth slice; FINRA TRACE/ETF premium-discount/CDS credit microstructure; and release-surprise history for economy pages. Paid-source parity should remain explicitly out of scope until the operator approves licensing.

## Alternatives Considered

- Keep all routes and add more badges. Rejected because the user asked for subtraction, and badges do not fix the false promise created by normal-looking proxy pages.
- Hide weak routes while keeping direct-link/deferred compatibility. Rejected because the user explicitly clarified that unnecessary surfaces should be completely cleaned with no compatibility code.
- Copy timsun.net page count one-for-one. Rejected because page count is not the product. The transferable idea is the decision chain, not the exact route inventory.
- Add a new macro worker for daily AI narrative. Rejected because deterministic read models already contain scenario and data-health fields, and the architecture avoids new workers without measured need.

## Boundaries

| Class | Behaviour |
|-------|-----------|
| Always | Preserve facts-first Macro Intel; keep provider calls outside the frontend and API request path; expose data gaps near the affected decision; hard-delete weak macro surfaces instead of hiding them. |
| Ask first | Adding paid data feeds, adding new persistent tables, or changing auth/config secret behavior. |
| Never | Print secrets, call external macro providers from React, fabricate data to make a route look ready, or treat repository examples as operator runtime config. |
