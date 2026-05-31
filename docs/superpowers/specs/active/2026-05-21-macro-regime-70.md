# Spec — Macro Regime 70

**Status**: Draft
**Date**: 2026-05-21
**Owner**: Codex
**Related**: `docs/superpowers/plans/active/2026-05-21-macro-regime-70.md`

## Background

The first macro slice established the correct product spine:

```text
macro_observations
  -> MacroViewProjectionWorker
  -> macro_view_snapshots
  -> /api/macro
  -> web /macro
```

That is the right boundary: provider fetching belongs in `macrodata-cli`, while
`parallax` persists normalized facts, computes deterministic regime
state, and exposes the latest state to operators and agents.

The current gap is that the real runtime is not yet an end-to-end macro regime
system. The production DB was observed at migration `20260521_0073`, while the
macro tables live in `20260521_0076`; therefore the live DB does not yet contain
`macro_observations` or `macro_view_snapshots`. The engine also uses only latest
observations, fixed thresholds, and thin panels. It has evidence/triggers/data
gaps, but not the deeper state-machine features from the target macro research
protocol.

## Problem

We need to move from a macro page scaffold to a 70+ quality macro state machine:

```text
public data sources
  -> agent-friendly macrodata-cli bundles
  -> imported observation facts
  -> historical feature layer
  -> deterministic regime engine
  -> scenario/trade-map JSON
  -> API/UI/agent consumption
```

The goal is not to replicate a third-party chart site. The goal is to reproduce
the macro reasoning protocol: liquidity, rates, Fed corridor, volatility,
credit, positioning, and cross-asset prices should confirm or reject a regime
claim.

## Quality Score Target

This project is considered a 70+ implementation when the following scorecard is
at least 70 points in a real local runtime, not only unit tests.

| Area | Max | 70+ requirement |
|------|-----|-----------------|
| Data source coverage | 20 | `macrodata-cli` can fetch a `macro-core` bundle covering liquidity, rates, Fed corridor, volatility, credit, cross-asset prices, and at least one positioning proxy. Partial provider failures are represented as structured data gaps. |
| Import chain | 15 | `parallax` can import a bundle into `macro_observations`, record import diagnostics, and run projection without manual SQL. |
| Historical feature layer | 15 | Engine can compute latest value, freshness, delta windows, z-score or percentile where history is available, and explicit insufficient-history gaps. |
| Regime state machine | 20 | Snapshot includes component scores, cross-panel confirmations, contradictions, hard triggers, regime label, and deterministic scenario/trade-map fields. |
| Product surface | 10 | `/api/macro` and `/macro` show regime, score, validation indicators, triggers, data gaps, source coverage, and scenario path without recomputing facts in UI. |
| Ops and verification | 20 | DB migration, CLI import, worker projection, API, and UI are covered by a documented end-to-end smoke test; no secrets are printed. |

Minimum passing target: **72/100**.

## Goals

- G1. Apply and verify the macro DB migrations in the real runtime path.
- G2. Extend `macrodata-cli` so agents can request one `macro-core` bundle
  rather than stitching rates/liquidity/credit/price data by hand.
- G3. Add a `parallax` importer that consumes `macrodata-cli` bundle
  envelopes and writes normalized `macro_observations`.
- G4. Add a historical feature layer that turns observations into changes,
  spreads, z-scores, percentiles, freshness diagnostics, and data-quality flags.
- G5. Upgrade the regime engine from latest-only panel scoring to a transmission
  chain:

  ```text
  energy/inflation impulse
    -> Fed corridor and rates
    -> onshore funding / liquidity
    -> credit intermediation
    -> volatility structure
    -> positioning and cross-asset confirmation
  ```

- G6. Emit deterministic scenario output:
  `current_regime`, `confirmations`, `contradictions`, `watch_triggers`,
  `invalidations`, `time_window`, `trade_map`, and `data_gaps`.
- G7. Keep LLMs downstream of deterministic JSON. Agents may summarize the
  snapshot, but they must not invent facts or recompute scores.

## Non-goals

- N1. Do not build institutional-only paid feeds in this phase: real
  CDX/CDS, full OPRA dealer gamma, Markit data, or proprietary cross-currency
  basis.
- N2. Do not make trading recommendations or position sizing decisions.
  `trade_map` means expression candidates and risk conditions, not advice.
- N3. Do not duplicate provider implementation inside `parallax`.
  Public provider fetching remains in `macrodata-cli`.
- N4. Do not block the 70+ milestone on perfect data coverage. Missing CFTC,
  Cboe, Stooq, or FRED series must degrade through `data_gaps`, not silent
  defaults.

## Data Layers

### Layer 1 — Provider Raw / Normalized Bundle

Owned by `macrodata-cli`.

Expected bundle:

```text
macro-core
  rates: DGS2, DGS5, DGS10, DGS30, T10Y2Y, T10Y3M, DFII10, T10YIE, T5YIFR
  fed_corridor: IORB, EFFR, DFEDTARU, DFEDTARL, SOFR
  liquidity: WALCL, WRBWFRBL, RRPONTSYD, TGA, SRF/RRP operations where available
  volatility: VIXCLS plus VIX term-structure proxies where public data is available
  credit: IG OAS, HY OAS, HY-IG spread source components
  cross_asset: SPY/SPX, QQQ/NDX proxy, IWM/RUT proxy, TLT, HYG, LQD, GLD, USO/WTI, BTC
  positioning: CFTC COT net-position proxy for at least one risk or rates market
```

The bundle must preserve source provenance, provider error codes, and freshness.
It may be partial; partial is acceptable only if consumers can see exactly what
is missing.

### Layer 2 — Observation Facts

Owned by `parallax`.

`macro_observations` remains the business fact table. Each imported observation
is idempotent by `(source_name, series_key, observed_at)`. An import run table
will record which bundle was consumed, coverage, errors, and timestamps.

### Layer 3 — Feature Layer

Owned by `macro_intel` services.

The projection worker reads a bounded history per series and computes:

- latest value and observed date;
- freshness in days;
- 5D, 20D, and 60D changes when available;
- z-score and percentile over a configurable lookback;
- spreads such as SOFR-IORB, HY-IG, 10Y-2Y, 10Y-3M, real-yield/breakeven;
- cross-asset confirmation pairs such as HYG/LQD, IWM/SPY, TLT/SPY, BTC/SPY.

Features may be embedded in `macro_view_snapshots` for the 70+ milestone. A
separate feature table is optional only if snapshot size or rebuild cost becomes
too high.

### Layer 4 — Regime Signals

Owned by `macro_regime_engine`.

The engine produces panel scores and chain-node scores:

| Node | Required behavior |
|------|-------------------|
| Liquidity | Net liquidity, SOFR-IORB, TGA/RRP pressure, reserve balance freshness, SRF/RRP operation gaps. |
| Rates | Front-end policy path, curve shape, real yield, breakeven/inflation impulse, term-premium proxy. |
| Fed corridor | Target range, IORB, EFFR/SOFR relationship, corridor breach triggers. |
| Volatility | VIX level, VIX change, public term-structure proxy when available, rate-vol proxy if available. |
| Credit | HY OAS, IG OAS, HY-IG, credit widening triggers, credit/equity confirmation. |
| Positioning | CFTC or other public positioning proxy; otherwise explicit `positioning_data_gap`. |
| Cross-asset | Equity, duration, credit ETF, commodity, dollar, and BTC confirmation/divergence. |

### Layer 5 — Scenario / Trade Map

Owned by deterministic report assembly, not LLM free text.

Each snapshot must include:

```json
{
  "scenario": {
    "current_regime": "funding_stress | term_premium_pressure | reflation | risk_on_liquidity | neutral | data_gap",
    "confidence": 0.0,
    "time_window": "3d | 1w | 2w | 1m",
    "confirmations": [],
    "contradictions": [],
    "watch_triggers": [],
    "invalidations": [],
    "trade_map": []
  }
}
```

`trade_map` entries are structured expressions such as "risk-on confirmed by
credit" or "duration under pressure from real-yield shock"; they must include
supporting indicator keys and invalidation triggers.

## Interface Contracts

### `macrodata-cli`

- `macrodata bundle macro-core --asof YYYY-MM-DD` returns latest available
  observations for all 70+ core series.
- `macrodata bundle history macro-core --start YYYY-MM-DD --end YYYY-MM-DD`
  returns a bounded history for those series, using the same observation shape.
- `macrodata mcp serve` exposes matching `bundle_macro_core` and
  `bundle_macro_core_history` tools.

### `parallax` CLI

- `parallax macro import-bundle --file PATH` imports a saved
  `macrodata-cli` result envelope.
- `parallax macro import-bundle --stdin` imports from stdin.
- `parallax macro project-once` runs `MacroViewProjectionWorker` once.
- `parallax macro status` reports migration readiness, observation
  counts, latest snapshot, source coverage, and current data gaps.

### Worker

- Add `macro_observation_import` only if automated CLI invocation is needed in
  the service runtime. The 70+ milestone may ship with operator-triggered CLI
  import first, but the design must not prevent a later worker.
- Keep `macro_view_projection` as the only writer to `macro_view_snapshots`.

### HTTP / UI

`GET /api/macro` continues to return latest deterministic state. It must add
the new `features`, `chain`, and `scenario` fields without breaking existing
`snapshot`, `panels`, `indicators`, `triggers`, `data_gaps`, and
`source_coverage` fields.

## Acceptance Criteria

- AC1. `uv run parallax db health` returns `migration_status=ready`
  in the operator runtime before macro smoke testing.
- AC2. With no observations, `parallax macro project-once` writes or
  returns a degraded deterministic snapshot rather than crashing.
- AC3. `macrodata bundle macro-core --asof <today>` returns a structured bundle
  with `coverage.requested >= 20` and partial diagnostics when providers are
  missing credentials.
- AC4. `parallax macro import-bundle --stdin` can import a
  `macrodata-cli` bundle and record import diagnostics without printing secret
  values.
- AC5. With at least rates/liquidity/vol/credit observations imported,
  `macro_view_projection` emits non-empty `features`, `chain`, and `scenario`.
- AC6. `/api/macro` returns `scenario.current_regime`,
  `scenario.confirmations`, `scenario.contradictions`,
  `scenario.watch_triggers`, and `scenario.trade_map`.
- AC7. `/macro` renders the 70+ structure: transmission chain, validation
  indicators, active triggers, contradictions, data gaps, and trade-map rows.
- AC8. The verification artifact includes the scorecard result and a real
  end-to-end command sequence:

  ```text
  macrodata bundle macro-core
    -> parallax macro import-bundle
    -> parallax macro project-once
    -> GET /api/macro
    -> open /macro
  ```

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| FRED key missing makes the score look worse than code quality | High | Show provider coverage and missing credentials explicitly; do not fail whole bundle when public no-key sources succeed. |
| Engine overfits fixed thresholds | High | Use percentile/z-score where history exists; keep hard thresholds only for corridor and stress overrides. |
| Macro data import becomes a second provider stack | Medium | Import only `macrodata-cli` envelopes; provider clients stay outside the app. |
| UI becomes another quote board | Medium | Render chain, confirmations, contradictions, and scenario fields before raw series tables. |
| CFTC/Stooq/Cboe public sources have inconsistent availability | Medium | Treat them as optional proxies with data gaps and source coverage, not required for core liquidity/rates readiness. |

## Evolution Path

After the 70+ milestone:

- Add Treasury auction tail / bid-to-cover / indirect bidder data.
- Add NY Fed RRP/SRF operation providers beyond catalog metadata.
- Add Cboe VIX term-structure provider or robust FRED/Cboe proxy set.
- Add crypto derivatives: BTC/ETH funding, OI, basis, options IV.
- Add LLM report generation that consumes only deterministic snapshot JSON.
- Backtest score weights and convert hard-coded thresholds into versioned
  calibrated regime definitions.

## Boundaries

| Class | Behavior |
|-------|----------|
| Always | Keep provider fetching in `macrodata-cli`, persist imported observations, compute deterministic features/signals, expose source coverage and gaps. |
| Ask first | Add paid data feeds, trading recommendations, automatic credential storage, or new external services. |
| Never | Invent missing macro values, silently treat data gaps as neutral, print secrets, or let UI/LLM recompute business facts. |
