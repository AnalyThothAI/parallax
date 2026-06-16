# Spec — Macro Decision Console

**Status**: Draft
**Superseded by**: Not superseded
**Date**: 2026-06-16
**Owner**: Codex
**Approved by**: Delegated goal from user on 2026-06-16
**Approved at**: 2026-06-16
**Related**: `docs/sdd/features/active/2026-06-16-macro-decision-console/plan.md`

## Background

Macro Intel is already a PostgreSQL-first read-model lane. Normal freshness is owned by macro sync, which runs the packaged macrodata-cli history bundle outside database transactions and persists normalized observations as macro observations; API routes and frontend pages must not call external providers directly (`src/parallax/domains/macro_intel/ARCHITECTURE.md:3`, `src/parallax/domains/macro_intel/ARCHITECTURE.md:24`). The public projection is macro regime v4, and module pages consume macro module view v3 fields for module read, evidence, transmission, data health, provenance, and related routes instead of recomputing conclusions in the UI (`src/parallax/domains/macro_intel/ARCHITECTURE.md:121`, `src/parallax/domains/macro_intel/ARCHITECTURE.md:152`, `src/parallax/domains/macro_intel/ARCHITECTURE.md:162`).

The current module catalog exposes 31 module ids, including routes whose content is mostly proxy data or explicit future gaps: auctions, Fed statements, Fed speeches, volatility dashboard, CDS proxy, global dollar, subsurface funding, consumer, and crypto derivatives (`src/parallax/domains/macro_intel/services/macro_module_catalog.py:41`, `src/parallax/domains/macro_intel/services/macro_module_catalog.py:327`, `src/parallax/domains/macro_intel/services/macro_module_catalog.py:383`, `src/parallax/domains/macro_intel/services/macro_module_catalog.py:644`, `src/parallax/domains/macro_intel/services/macro_module_catalog.py:676`). The frontend navigation already hides some weak labels while still keeping their module configs, related-route targets, fixtures, and direct route behavior (`web/src/features/macro/model/macroNavigationTree.ts:121`, `web/src/features/macro/model/macroNavigationTree.ts:148`, `web/src/features/macro/model/macroNavigationTree.ts:278`, `web/src/features/macro/model/macroNavigationTree.ts:303`).

The macrodata bundle currently covers 128 provider series across liquidity, rates, economy, volatility, credit, assets, and CFTC positioning (`src/parallax/domains/macro_intel/_constants.py:11`, `src/parallax/domains/macro_intel/_constants.py:149`). Parallax runtime reports the operator config at /Users/qinghuan/.parallax/config.yaml, workers config at /Users/qinghuan/.parallax/workers.yaml, macrodata enabled, and FRED configured through the FINANCE_FRED_API_KEY env name. Live macro status on 2026-06-16 reports 63,407 observations, 128 concepts, no projection lag, and latest snapshot status partial; the blocking issue is history coverage 0.8425 with 20 concepts below minimum history, not a missing projection (`docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md:17`).

The standalone macrodata-cli checkout has no FRED_API_KEY configured. Running uv run macrodata bundle macro-core --asof 2026-06-16 in that checkout returned only 67 available series out of 128 and marked the bundle partial because many FRED public CSV requests timed out. The external FRED provider currently switches to public CSV when no API key exists and uses a per-request HTTP client with the same timeout for every FRED series (`docs/sdd/features/active/2026-06-16-macro-decision-console/verification.md:19`).

External benchmark: timsun.net presents US macro as a decision console, not only as indicator pages. Its home page surfaces Macro State, a Trade Map, data-quality watch, the three most important changes, confirmation/divergence, liquidity pressure, future catalysts, and watchlist triggers. Its first-level sections for assets, rates, liquidity, volatility, and credit each reduce data into daily interpretation, source/as-of evidence, and validation triggers. The product gap is therefore not just missing series; the larger gap is failure to compress cross-asset facts into a usable decision chain (https://timsun.net/, https://timsun.net/trade-map).

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
- G2. Public macro surface is reduced to source-backed modules only: Overview, Assets, Rates/Fed Funds, Rates/Yield Curve, Rates/Real Rates, Rates/Expectations, Liquidity/Transmission, Liquidity/RRP-TGA, Volatility/VIX, Credit/Stress, and Economy/Inflation/Employment/GDP. Removed modules no longer exist as supported module ids.
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
- Research Backlog: unavailable domains such as Treasury auction results, Fed text/speaker calendar, MOVE, VIX futures curve, SLOOS, loan quality, ETF premium/discount, TRACE, cross-currency basis, and Fed funds futures are documented as source gaps. They have no runtime route until implemented.

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
- Web `/macro`: renders only backend-provided macro decisions, data health, charts, and tables for retained modules.

## Acceptance criteria

- AC1. WHEN a user hard-loads `/macro` THEN the system SHALL show current macro state, confidence, top changes, confirmation/divergence, watch triggers, invalidations, trade map, and data health without requiring a child route.
- AC2. WHEN a user opens macro navigation THEN the system SHALL show only source-backed primary routes and SHALL not include auctions, Fed statements, Fed speeches, volatility dashboard, CDS proxy, global dollar, subsurface funding, consumer, or crypto derivatives in any navigation, related-route list, fixture, or module catalog.
- AC3. WHEN a deleted macro route is opened directly THEN the system SHALL use the ordinary not-found behavior and SHALL not render a legacy, hidden, deferred, or compatibility module shell.
- AC4. WHEN FRED public CSV is unavailable or timed out in standalone macrodata-cli THEN `bundle macro-core` SHALL return source-health diagnostics that identify FRED fallback mode and affected series without dropping available NY Fed, Treasury, Yahoo, and CFTC observations.
- AC5. WHEN Parallax runtime has `FINANCE_FRED_API_KEY` configured THEN macro status SHALL report FRED configured through a redacted boolean and macrodata bundle availability without exposing the key.
- AC6. WHEN the implementation is verified THEN frontend lint, architecture tests, typecheck, targeted macro component tests, macro Python tests, and macrodata-cli tests SHALL pass or list a concrete baseline blocker.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Removing historical URLs breaks bookmarks for power users. | Medium | Accepted by product direction; tests assert hard deletion so the break is explicit instead of accidental. |
| Decision console duplicates existing module logic. | High | Build from persisted `scenario_json`, `chain_json`, `features_json`, `scorecard_json`, and `data_health`; do not compute scores in frontend. |
| FRED public CSV is slow enough to block bundles. | High | Prefer API-key mode in runtime, add source-mode diagnostics, tune bounded timeout/retry/concurrency, and keep partial coverage honest. |
| Data-source backlog expands beyond one feature. | Medium | Record source gaps and split provider additions into successor SDD records. |
| UI changes violate frontend CSS ownership harness. | Medium | Keep CSS under `web/src/features/macro/ui/...`, run `npm run lint`, `npm run test:architecture`, and `npm run typecheck`. |

## Evolution Path

After this feature, successor records should add public-source coverage in priority order: Treasury auction results/calendar, FOMC calendar/statements/minutes/speeches, VIX futures or CBOE term-structure source, MOVE proxy, Fed funds futures or CME/FedWatch-compatible public alternative if legally usable, SLOOS and loan-quality FRED series, OFR stress, and ETF premium/discount/TRACE proxies. Paid-source parity should remain explicitly out of scope until the operator approves licensing.

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
