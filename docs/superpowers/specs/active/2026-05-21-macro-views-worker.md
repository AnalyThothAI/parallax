# Spec — Macro Views Worker

**Status**: Approved
**Date**: 2026-05-21
**Owner**: Codex
**Related**: `docs/superpowers/plans/active/2026-05-21-macro-views-worker.md`

## Background

`gmgn-twitter-intel` is PostgreSQL-first: facts and rebuildable read models are the durable truth, and workers re-read the database rather than trusting wake hints (`docs/ARCHITECTURE.md:33`, `docs/ARCHITECTURE.md:59`, `docs/WORKERS.md:10`, `docs/WORKERS.md:41`). The current worker inventory already contains read-model projection workers such as `news_page_projection` and `cex_oi_radar_board`, each with one runtime writer and API readers (`docs/WORKERS.md:111`, `docs/WORKERS.md:112`, `src/gmgn_twitter_intel/app/surfaces/api/http.py:24`). The frontend route shell is centralized in `web/src/routes/AppRoutes.tsx:242`, and the side rail currently exposes Radar, Stocks, and News inside a `views` section (`web/src/features/cockpit/ui/CockpitSideRail.tsx:49`).

The separate `macrodata-cli` package now owns public macro source access and normalization. This service should not duplicate provider fetching in the first integration; it should persist normalized macro observations and project them into a product-facing macro state view.

## Problem

The application has crypto/social intelligence, news, stock radar, and CEX derivative views, but no macro context page that explains whether a token or market move is occurring inside easing liquidity, funding stress, rate shock, vol stress, or credit divergence. Agents also lack a stable HTTP/UI contract for macro regime state inside this service.

## First principles

- Facts and projections stay separate: normalized macro observations are facts, and macro view snapshots are rebuildable read models (`docs/ARCHITECTURE.md:33`, `docs/WORKERS.md:44`).
- A macro view read model has exactly one runtime writer, matching the existing projection-worker rule (`docs/ARCHITECTURE.md:59`, `docs/WORKERS.md:51`).
- LLMs must not invent macro facts; the worker emits deterministic scores, evidence, triggers, and data gaps from persisted observations.

## Goals

- G1. A worker run with no macro observations still produces an observable degraded snapshot so API and UI can show a deterministic data-gap state.
- G2. A worker run with representative liquidity, rates, credit, and volatility observations produces a persisted snapshot with component scores, regime label, indicators, triggers, and source coverage.
- G3. `/api/views/macro` returns the latest snapshot through the authenticated API envelope, and `/views` renders it through a React Query feature hook.
- G4. The feature is small enough to verify with targeted backend unit tests and frontend component/route tests before attempting the full repository gate.

## Non-goals

- N1. This does not add live FRED, NY Fed, Treasury, Cboe, CFTC, or crypto provider fetching inside `gmgn-twitter-intel`; those remain owned by `macrodata-cli` or future ingestion work.
- N2. This does not implement institutional-only data such as real CDX/CDS, OPRA dealer gamma, MOVE, or cross-currency basis.
- N3. This does not generate LLM macro commentary. The snapshot is deterministic JSON that future agents may summarize.
- N4. This does not make macro scores trading recommendations.

## Target Architecture

Add a new `macro_intel` bounded context. It owns normalized macro observations, a deterministic macro regime engine, a `macro_view_projection` worker, a read repository, and an API route under `/api/views/macro`.

The worker reads latest observations by curated series keys, computes a compact Macro Regime Engine snapshot, and writes `macro_view_snapshots`. The first MVP focuses on five panels: liquidity, rates, volatility, credit, and cross-asset confirmation. Each panel carries a score, status, supporting indicators, and data gaps. The frontend adds `/views` as a compact operator dashboard in the existing cockpit shell.

## Conceptual Data Flow

```text
macrodata-cli output / future importer
  -> macro_observations facts
  -> MacroViewProjectionWorker
  -> macro_view_snapshots read model
  -> /api/views/macro
  -> web /views
```

The changed arrow is independent of the GMGN ingest chain because macro observations are external market facts, not token events. The worker follows the existing projection pattern and never calls providers directly.

## Core Models

- `MacroObservation`: normalized fact keyed by source and series. It stores `series_key`, `observed_at`, numeric value, unit, frequency, data quality, source timestamp, and raw payload reference.
- `MacroViewSnapshot`: rebuildable read model for one computed macro state. It stores `snapshot_id`, `asof_date`, `status`, `regime`, `overall_score`, component score map, indicator map, trigger list, data gaps, source coverage, and `computed_at_ms`.
- `MacroPanelScore`: deterministic component output for liquidity, rates, volatility, credit, and cross-asset confirmation.

## Interface Contracts

- HTTP: `GET /api/views/macro` requires the existing bearer/query token. It returns `{ ok: true, data: { snapshot, panels, triggers, data_gaps } }`; if no worker snapshot exists it returns a `snapshot: null` data-gap response rather than provider calls.
- Worker: `macro_view_projection` is a canonical worker with an advisory lock, bounded interval catch-up, and no wake dependency in the MVP.
- UI: `/views` renders the latest macro state, with explicit empty/error/loading states and no local recomputation of scores.

## Acceptance Criteria

- AC1. WHEN `MacroViewProjectionWorker.run_once_sync()` runs against an empty observation set THEN it SHALL write a degraded snapshot with data gaps and no exception.
- AC2. WHEN representative observations include WALCL, RRP, TGA, SOFR, IORB, DGS2, DGS10, VIX, HY OAS, and IG OAS THEN the worker SHALL write component scores and trigger/evidence JSON derived only from those observations.
- AC3. WHEN an authenticated request calls `/api/views/macro` THEN the API SHALL return the latest snapshot envelope without provider IO.
- AC4. WHEN a user opens `/views` THEN the frontend SHALL fetch `/api/views/macro` and render regime, component panels, validation indicators, triggers, and data gaps.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Scores look precise without enough data | High | Emit data gaps, source coverage, and `status=partial|empty`; keep weights transparent. |
| Duplicating `macrodata-cli` providers in the app | Medium | MVP worker reads only persisted observations; no provider clients in this service. |
| New read model violates single-writer rule | Medium | Declare `macro_view_projection` in worker registry, docs, and domain architecture. |
| UI turns into a quote board | Medium | Page groups indicators into regime panels, triggers, and validation evidence instead of raw prices only. |

## Evolution Path

Next work should add an importer that consumes `macrodata-cli bundle` envelopes into `macro_observations`, then expands panels with CFTC positioning, Cboe VIX structure, Treasury auctions, crypto derivatives, and cross-asset confirmation. The schema should not assume one provider per metric or one observation per day.

## Alternatives Considered

- API-only on-demand scoring — rejected because macro scoring should be reproducible and visible in worker status, not recomputed inside HTTP requests.
- Provider calls inside `gmgn-twitter-intel` — rejected because `macrodata-cli` already owns provider normalization and agent-oriented data-source CLI behavior.
- Frontend-only macro dashboard fed by static fixtures — rejected because the app needs a durable contract that agents and workers can inspect.

## Boundaries

| Class | Behaviour |
|-------|-----------|
| Always | Persist normalized macro facts, project deterministic snapshots, expose latest snapshot through API and `/views`. |
| Ask first | Add live provider fetchers, paid data sources, LLM commentary, or trading recommendations. |
| Never | Invent missing macro values, call provider APIs from the view route, or let UI recompute ranking/regime scores. |
