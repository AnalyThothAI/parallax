# Spec — Macro Intel Workbench Redesign

**Status**: Superseded
**Date**: 2026-06-09
**Owner**: Codex
**Superseded by**: `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut/`
**Related**: `docs/FRONTEND.md`, `docs/DESIGN_DISCIPLINE.md`, `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/sdd/features/completed/2026-06-09-macro-intel-redesign/macro-visual-mockup.html`

## Background

Macro Intel is a deterministic read-model product. The backend architecture states that macro pages consume `macro_module_view_v3` and render display-ready `module_read`, `module_evidence`, `transmission`, `data_health`, provenance, and related routes without recomputing conclusions in the UI (`src/parallax/domains/macro_intel/ARCHITECTURE.md:98-112`). The frontend contract repeats that `/macro` and child routes read `/api/macro`, `/api/macro/modules/{module_id}`, and module-adjacent endpoints such as asset correlation; macro shell/sidebar code owns navigation and module pages must not recompute macro scoring or module reads (`docs/FRONTEND.md:70-76`).

The current route shell is correctly scoped to Macro Intel and passes macro module payloads into page renderers (`web/src/features/macro/MacroWorkbenchRoute.tsx:56-91`). The current page grammar is not yet a coherent product surface:

- The overview page renders read, metric strip, market board, transmission, and health as equal panels, so the user must infer the hierarchy instead of reading a clear desk brief first (`web/src/features/macro/ui/pages/MacroOverviewModulePage.tsx:24-54`).
- Generic leaf pages stack metric strip, chart/table, optional tables, read, transmission, evidence, source table, and data health with the same weight; this makes a module feel like a payload dump rather than an analyst workflow (`web/src/features/macro/ui/pages/MacroLeafModulePage.tsx:35-84`).
- The asset landing page improved toward a dashboard first structure, but it is still a 500-line page component with grouping, daily brief parsing, correlation query rendering, diagnostics, and local table formatting mixed together (`web/src/features/macro/ui/pages/MacroAssetOverviewPage.tsx:45-148`, `web/src/features/macro/ui/pages/MacroAssetOverviewPage.tsx:159-220`).
- Rates has a clearer workbench path, but it remains visually separate from generic macro pages and uses a dedicated CSS surface that cannot become the common product grammar without refactoring (`web/src/features/macro/ui/rates/MacroRatesModulePage.tsx:28-37`, `web/src/features/macro/ui/rates/macroRatesWorkbench.css:1-220`).
- Test coverage still preserves old assumptions in places; the route test currently says mobile and tablet macro pages should not render the module navigation, contradicting the desired clear macro module navigation model (`web/tests/routes/macro.route.test.tsx:193-205`).

The current codebase already has reusable primitives, TanStack table support, deterministic chart wrappers, correlation tables, and macro route metadata. The redesign should reuse those capabilities where they fit, but it should not keep old page layouts for compatibility.

## Problem

Macro Intel is difficult to use because pages present too many equally weighted panels, repeat concepts under different labels, and lack a consistent desk workflow from "what changed" to "what do I inspect next". A market analyst cannot quickly answer: current regime, cross-asset state, which module matters, whether the data is trustworthy, and where to drill down.

## First principles

1. **Backend facts are the product truth.** The UI renders `macro_module_view_v3` and module-adjacent read models; it never re-scores or invents macro conclusions. This is enforced by the macro architecture and frontend contract (`src/parallax/domains/macro_intel/ARCHITECTURE.md:98-112`, `docs/FRONTEND.md:70-76`).
2. **Each page has one primary user question.** Overview answers "what is the macro tape saying now"; asset landing answers "what are the major markets doing"; leaf modules answer "what changed in this module and why"; rates answers "what is the rates path and policy constraint"; correlation answers "which assets are moving together".
3. **Data quality is visible but subordinate.** Sparse coverage and stale facts must be shown as readiness/gaps, not hidden, but diagnostics should not compete with the primary market read (`src/parallax/domains/macro_intel/ARCHITECTURE.md:89-100`).

## Goals

- G1. The macro workbench has a single visual grammar: shell navigation, section rail, primary read strip, market evidence area, interpretation area, and diagnostics drawer/section.
- G2. Every visible macro page has a first-screen answer to its primary question without requiring the user to scan more than three panels.
- G3. Asset and market tables use consistent columns, numeric alignment, source/date visibility, and stable drill-down affordances.
- G4. Page component ownership is split so no macro page component exceeds 220 lines after implementation, except model files that are pure derivation and explicitly justified.
- G5. Tests assert the new product grammar and remove assertions that preserve retired navigation or panel order.

## Non-goals

- N1. No backend schema, worker, score, projection, or API contract changes.
- N2. No new external UI component library. Existing React, Radix, TanStack Table, lightweight-charts, and local primitives are sufficient.
- N3. No compatibility layer for old macro panel order, old mobile navigation assumptions, or retired CSS selectors.
- N4. No live real-data debugging in this phase; real-data verification remains governed by `uv run parallax config` and operator config rules.

## Target architecture

The target frontend is a "Macro Research Workbench" with five page families:

1. **Overview Command Page.** A desk brief at the top summarizes regime, confidence/readiness, as-of state, and the two or three drivers that matter. Under it, a compact cross-domain board shows assets, rates, liquidity, volatility, credit, and economy as comparable rows. Transmission and diagnostics appear below as supporting evidence.
2. **Asset Command Page.** A market dashboard first: equities, bonds, commodities, FX, and crypto are grouped in dense tables with the same columns. Daily judgment, correlation preview, and data diagnostics follow.
3. **Generic Module Page.** A reusable module template replaces the current generic leaf stack. It has a page read strip, primary visual/evidence board, driver/evidence lanes, and diagnostics. The same component handles assets leaf pages, liquidity, economy, volatility, credit, and secondary pages.
4. **Rates Workbench Page.** Rates keeps specialized charts and policy framing, but adopts the same workbench grammar: read strip, fact table, primary visual, decision lanes, details, diagnostics.
5. **Correlation Matrix Page.** Correlation becomes a focused matrix workspace with window controls, matrix, strongest pairs, coverage, and gaps. It uses the same page shell and diagnostics semantics.

The implementation should introduce a small macro workbench UI system: page frame, section rail metadata, read strip, compact fact table, evidence lane, diagnostics summary, and module drill-down list. Existing primitives can be retained only if they conform to the new grammar; otherwise they should be deleted or replaced.

## Conceptual data flow

```text
macro_sync -> macro read models -> /api/macro/modules/{module_id}
  -> feature API hooks
  -> pure macro view models
  -> Macro Workbench UI grammar
  -> analyst reads, drills down, checks diagnostics
```

Only the last two arrows change. Backend reads and payload semantics stay fixed.

## Core models

- **Macro Workbench Page.** A rendered page with title, question, status, primary read, primary data surface, evidence lanes, diagnostics, and drill-down metadata.
- **Macro Read Strip.** The first-screen interpretive object: headline, regime/confidence/readiness labels, as-of date, and short explanation.
- **Macro Market Row.** A display row with label, symbol/code, latest, day or window change, observed date, source/readiness, and drill-down target when applicable.
- **Macro Evidence Lane.** A grouped list of confirmations, contradictions, watch triggers, invalidations, or module-specific decision facts.
- **Macro Diagnostics Summary.** Module status, source count, gap count, stale/fresh state, and compact gap list. Detailed source tables remain available but are not a first-screen competitor.

## Interface contracts

No public API changes. The frontend continues reading:

- `/api/macro/modules/{module_id}` for macro module pages.
- `/api/macro/series` for chart concepts declared by the module payload.
- `/api/macro/assets/correlation` for the correlation page and asset preview.

The UI contract changes: pages must present backend fields through the workbench grammar rather than the current panel stack. Missing data renders explicit empty or diagnostic states with accessible names and no silent fallback to invented conclusions.

## Acceptance criteria

- AC1. WHEN `/macro` loads with a valid overview module THEN the first macro content region SHALL be a desk brief containing headline, regime/readiness, as-of, and driver summary.
- AC2. WHEN `/macro/assets` loads THEN the first macro content region SHALL be a market dashboard with equities, bonds, commodities, FX, and crypto groups before judgment, correlation, or diagnostics.
- AC3. WHEN any non-rates leaf module loads THEN the page SHALL use the generic module workbench grammar and SHALL NOT render the old sequence `关键指标 -> 市场板 -> 模块判断 -> 传导链 -> 模块证据 -> 数据来源 -> 模块数据健康`.
- AC4. WHEN rates module pages load THEN they SHALL share the same shell/read/diagnostics grammar as other macro pages while retaining rates-specific visualizations.
- AC5. WHEN `/macro/assets/correlation` loads THEN matrix, strongest positive/negative pairs, coverage, and gaps SHALL use shared correlation components and one consistent tone scale.
- AC6. WHEN the macro route renders at 390px, 834px, 1366px, and 1920px THEN no macro page SHALL create document horizontal overflow or overlapping text.
- AC7. WHEN architecture tests scan macro CSS THEN no retired macro selectors or stale compatibility test assumptions SHALL remain.
- AC8. WHEN the visual mockup is opened THEN it SHALL show the target overview, asset dashboard, generic module, rates, and correlation page shapes in one coherent system.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| The redesign hides data-quality gaps behind a cleaner UI. | High | Diagnostics summary is required on every page and detailed source/gap tables remain reachable below the primary read. |
| A generic page grammar erases rates-specific analysis. | Medium | Rates keeps specialized chart and decision-support components while adopting the shared shell/read/diagnostics grammar. |
| Reducing panel count drops backend evidence. | Medium | Evidence lanes consume the same `module_evidence`, `transmission`, provenance, and data-health records; only layout and priority change. |
| Tests pass because they are too narrow. | Medium | Add route, component, architecture, and Playwright assertions for page order, mobile reachability, and no-overflow. |
| The visual system becomes decorative instead of operational. | Medium | Use dense tables, restrained color, source/date visibility, and no marketing hero layout. |

## Evolution path

The next expansion is a saved "macro watch view" that pins selected modules and correlations for an operator. The redesign should not foreclose that by baking route-local layout assumptions into each page. Workbench components should receive semantic page view models and remain reusable across pinned layouts.

## Alternatives considered

- **Retain current pages and tweak CSS.** Rejected because the problem is information architecture: panel order and repeated semantics are wrong, not merely styling.
- **Copy `timsun.net/assets/` literally.** Rejected because it is a server-rendered assets board, while Parallax is a React macro research workbench with deterministic backend module reads. The useful lesson is market-table-first hierarchy, not implementation shape.
- **Introduce a new dashboard library.** Rejected because existing Radix, TanStack Table, lightweight-charts, and local primitives cover the required interaction and rendering. A new dependency would not solve the product grammar problem.

## Boundaries

| Class | Behaviour |
|-------|-----------|
| Always | Use backend display-ready macro payloads; prioritize first-screen analyst read; show data readiness; keep route navigation clear; delete old compatibility tests and selectors. |
| Ask first | Backend API shape changes, new persistent read models, real-data provider debugging, or adding a new dependency. |
| Never | Recompute macro scores or reads in the frontend; keep old panel order compatibility; hide stale/missing data; create a marketing landing page for Macro Intel. |
