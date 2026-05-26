# Spec — Macro Responsive UI Layout Hard Cut

**Status**: Proposed
**Date**: 2026-05-26
**Owner**: qinghuan / Codex
**Related**:
- `docs/superpowers/specs/active/2026-05-26-macro-terminal-ui-navigation-hard-cut-cn.md`
- `docs/superpowers/plans/active/2026-05-26-macro-terminal-ui-navigation-hard-cut-plan-cn.md`
- `timsun-assets-snapshot.md`

## Background

The previous macro navigation hard cut moved the macro tree into the application sidebar and removed page-local macro tabs. That is now structurally correct, but the macro content area still uses layout rules that were written for a smaller set of cards rather than for a dense, responsive research terminal.

Current macro page rendering is concentrated in `web/src/features/macro/ui/pages/MacroModulePageFrame.tsx:48-175` for leaf pages and `web/src/features/macro/ui/pages/MacroModulePageFrame.tsx:178-260` for the overview page. The same file also owns many local rendering primitives such as section headers, KPI tiles, read rows, evidence groups, transmission nodes, data health buckets, and chart selection. This makes page semantics, data rendering, and layout behavior hard to reason about independently.

The current page CSS is concentrated in `web/src/features/macro/ui/pages/macroPages.css:1-479`. The CSS defines a 12-column page grid, generic panel spans, KPI strips, table/chart grids, evidence grids, and mobile media rules in one owner file. The rule `.macro-page-panel-current { grid-column: span 7; }` at `web/src/features/macro/ui/pages/macroPages.css:33-35` creates an orphan left card on the overview page when no right-side companion is placed beside it. KPI cards use `overflow-wrap: anywhere` for labels at `web/src/features/macro/ui/pages/macroPages.css:161-167` and values at `web/src/features/macro/ui/pages/macroPages.css:169-175`, which causes short symbols and words such as `SPX`, `VIX`, `CPI`, and `Payrolls` to break vertically in narrow cards.

The macro shell header is owned by `web/src/features/macro/ui/shell/MacroPageHeader.tsx:13-30` and styled in `web/src/features/macro/ui/shell/macroShell.css:23-97`. The status block uses a fixed two-column, minimum-width shape at `web/src/features/macro/ui/shell/macroShell.css:83-90`; it works in some widths, but the visual hierarchy is brittle around compact desktop/tablet widths and becomes a tall stacked block on mobile.

The correlation route is a special surface. It renders a separate page shell in `web/src/features/macro/MacroAssetCorrelationPage.tsx:38-106`, with its own header, controls, matrix, cards, and CSS. It does not use `MacroShell` or `MacroPageHeader`, so `/macro/assets/correlation` has different heading, breadcrumb, and status behavior from other macro child routes.

The frontend architecture contract requires macro shell/sidebar code to own macro navigation and module pages to render deterministic `macro_module_view_v3` fields directly. It also requires responsive behavior to be a tested architecture surface, with desktop starting at `1280px`, tablet from `768px` through `1279px`, and mobile at `max-width: 767px`; see `docs/FRONTEND.md`.

Browser audit on the running Docker app (`http://127.0.0.1:8765`) covered 32 macro routes at `1096x690`, `1366x720`, `834x1194`, and `390x844`. The audit found no body-level horizontal overflow, but found repeated content-level defects:

- `/macro` at 1366 shows the overview read card as a 7-column orphan with a large empty right side in the first viewport.
- KPI labels break into vertical fragments on several routes and widths, including `SPX`, `VIX`, `CPI`, `Payrolls`, `Claims`, `DXY`, `SOFR`, and credit OAS labels.
- Mobile leaf pages often rely on internal table wrappers that scroll horizontally, but the UI gives no clear scroll affordance or sticky context.
- `/macro/assets/correlation` is visually stronger than many generic pages, but it is semantically detached from the macro shell and has its own responsive behavior.
- Long leaf pages such as `/macro/rates/yield-curve` produce very tall mobile pages because every observation becomes a full KPI card instead of a compact, domain-specific summary.

## Problem

The macro UI now has the right navigation location but not the right layout system. Page types are not explicit, reusable visual primitives are buried inside page frames, and CSS rules are trying to serve overview, index, leaf, and correlation pages at once. The result is a terminal that looks partially hard-cut but still feels assembled from uneven card grids: first-view information density is inconsistent, labels break awkwardly, mobile/tablet layouts are technically reachable but not polished, and correlation has a different shell grammar from the rest of macro.

## First Principles

1. **Macro pages answer module-local questions; navigation lives in shell/sidebar.** This is the existing hard-cut invariant from `docs/FRONTEND.md` and from `web/src/features/cockpit/ui/appNavigation.ts`, which adapts `MACRO_NAVIGATION_TREE` into the app sidebar. This work must not restore page-local macro navigation.
2. **Frontend renders backend facts; it does not reinterpret macro scoring.** Macro pages consume `module_read`, `module_evidence`, `transmission`, `data_health`, `provenance`, and `section_boards` directly. This work may reshape visual presentation, but it must not recompute module reads, ranking, health, or evidence from raw indicators.
3. **Responsive layout is a contract, not a patch.** Breakpoint behavior must be verified at `390`, `430`, `834`, `1096`, `1366`, and `1920` widths. Text must not overlap, clip, or split into unreadable fragments, and horizontal scrolling must be intentional, bounded, and discoverable.

## Goals

- G1. Every macro route in `MACRO_NAVIGATION_TREE`, including hidden-but-supported routes, renders without body-level horizontal overflow at `390`, `430`, `834`, `1096`, `1366`, and `1920` widths.
- G2. The `/macro` overview first viewport uses the full available content width at desktop and compact desktop sizes; it must not show an orphan left card with unused right-side space.
- G3. KPI and metric labels never split single short tokens vertically. Symbols and compact labels such as `SPX`, `VIX`, `CPI`, `SOFR`, `DXY`, `HY OAS`, and `Payrolls` remain readable on desktop, tablet, and mobile.
- G4. Overview, asset index, leaf module, and correlation pages each have an explicit page kind and layout contract. Shared components can be tested independently from module-specific route wrappers.
- G5. Tables and matrices remain dense on desktop and usable on mobile through bounded scroll containers, sticky context where useful, and visible scroll affordances.
- G6. The macro page CSS remains within the frontend architecture harness constraints and is split by owner responsibility; no new retired buckets, global compatibility styles, or cross-feature selector coupling are introduced.

## Non-goals

- N1. No backend API, database, worker, projection, or macro scoring changes.
- N2. No change to the `macro_module_view_v3` contract.
- N3. No restoration of macro header tabs or page-local full navigation.
- N4. No redesign of non-macro pages except where the shared shell/topbar contract must be measured during macro verification.
- N5. No compatibility layer for old selectors such as retired macro tab classes; this is a hard cut.
- N6. No new charting library, design system dependency, or visual theme reset.

## Current Page Audit

| Page group | Current behavior | Required product direction |
|------------|------------------|----------------------------|
| `/macro` overview | Uses overview frame but inherits generic panel spans. At desktop, the first card occupies the left portion and leaves a large blank right region. KPI labels inside the card can split vertically. | Become the command summary page: one full-width first-view composition with read, status, coverage, key metrics, and data health arranged as a purposeful terminal surface. |
| `/macro/assets` index | Dense matrix is closer to the target. Mobile uses internal horizontal scroll. | Keep matrix model, but add scroll affordance, stable column sizing, and a clearer first-screen relation between summary counts and rows. |
| Asset leaf pages | Stronger than overview at desktop; cards and market board use the width well. Mobile stacks correctly but becomes very long. | Keep leaf grammar but replace generic KPI cards with a metric strip that preserves label readability and uses compact rows for many observations. |
| Rates pages | Yield curve and rate modules can expose many observations as many cards; mobile becomes especially tall. | Add domain-aware metric density: curve/rate pages should summarize term structure first, then table the rest. |
| Liquidity and economy pages | Long numeric values and long labels stress the KPI card shape. | Add number/value formatting constraints and a metric component that supports long units without breaking labels. |
| Volatility and credit pages | Short labels are often narrow enough to split; credit pages show many OAS metrics. | Use a compact metric table/list variant when metric count exceeds the card threshold. |
| `/macro/assets/correlation` | Visually coherent but detached from `MacroShell`; uses its own header, layout, and responsive logic. | Bring it into the macro shell grammar while preserving the matrix-specific dense interaction. |
| Hidden supported pages | Not shown in primary sidebar, but still addressable. | Keep addressable only if they render a meaningful module state. If a page is only a proxy stub, it should have an explicit secondary/hidden product tier and a consistent unavailable/data-gap surface. |

## Route Audit Inventory

The implementation plan must treat this as the minimum route-by-route audit surface. Each page gets a product role before visual work begins; low-value pages are not allowed to drive shell or layout complexity.

| Route | Product role | Current audit finding | Required UI direction |
|-------|--------------|-----------------------|-----------------------|
| `/macro` | Primary overview | First viewport is visually unbalanced; overview panel does not use available width; metric tokens split. | Replace generic overview card grid with a full-width command summary composition. |
| `/macro/assets` | Primary index | Best current density; mobile matrix scroll is bounded but under-signaled. | Keep dense matrix, add explicit table/matrix frame behavior and scroll affordance. |
| `/macro/assets/equities` | Primary leaf | Desktop layout is closer to target; KPI card labels can still fragment. | Use shared leaf renderer and metric strip/list components. |
| `/macro/assets/bonds` | Primary leaf | Same generic KPI/card grammar as equities; labels and long units can stress cards. | Use shared leaf renderer with compact metric density rules. |
| `/macro/assets/commodities` | Primary leaf | Same generic KPI/card grammar; page can become a long card stack. | Use shared leaf renderer; keep market board dense before evidence. |
| `/macro/assets/fx` | Primary leaf | DXY and cross-asset labels are vulnerable to narrow-card wrapping. | Use readable short labels and compact metric rows where needed. |
| `/macro/assets/crypto` | Primary leaf | Short labels and date/meta text compete in KPI tiles. | Use metric component with fixed label/value/date zones. |
| `/macro/assets/crypto-derivatives` | Secondary leaf | Specialist route; can be useful but should not dominate primary navigation density. | Keep as supported analytical page with compact derivatives-specific metrics. |
| `/macro/assets/correlation` | Primary matrix | Stronger matrix surface but detached from macro shell/header grammar. | Rehost under macro shell/header primitives while preserving matrix interaction. |
| `/macro/rates` | Primary category leaf | Generic module page; rates need curve-first synthesis. | Use rates summary layout before full detail panels. |
| `/macro/rates/fed-funds` | Primary leaf | Rate labels and values need compact, scan-friendly layout. | Use rate metric strip plus table/detail frame. |
| `/macro/rates/yield-curve` | Primary leaf | Many observations become tall KPI stacks on mobile. | Summarize curve shape first; move long observation sets into compact table/list. |
| `/macro/rates/real-rates` | Primary leaf | Long labels/units stress generic KPI tiles. | Use compact metric rows with stable label zones. |
| `/macro/rates/expectations` | Primary leaf | Expectation labels can be long and ambiguous in card grids. | Use ordered metric list and evidence panels after summary. |
| `/macro/fed` | Primary category leaf | Category page risks repeating subpage navigation semantics. | Render as module read page, not a local navigation page. |
| `/macro/liquidity` | Primary category leaf | Important but can become a tall generic card collection. | Use liquidity plumbing summary, then transmission/evidence panels. |
| `/macro/liquidity/transmission-chain` | Primary leaf | Transmission semantics are core but currently share generic panel grammar. | Give transmission a first-class panel component with dense nodes. |
| `/macro/liquidity/fed-balance-sheet` | Primary leaf | Long balance-sheet labels and values need stable wrapping. | Use compact metric rows and table frame. |
| `/macro/liquidity/operations` | Primary leaf | Operational data needs density and source clarity. | Prefer table/detail panels over many KPI cards. |
| `/macro/liquidity/rrp-tga` | Primary leaf | Short labels and multiple balances can fragment in narrow cards. | Use labeled metric rows with date/meta aligned separately. |
| `/macro/liquidity/reserves` | Primary leaf | Similar metric-density pressure as RRP/TGA. | Use same liquidity metric primitive. |
| `/macro/liquidity/global-dollar` | Secondary leaf | Useful specialist route but can feel detached if generic. | Keep supported with explicit secondary product tier and dense source panels. |
| `/macro/liquidity/subsurface` | Secondary leaf | Specialist route; may read like an internal proxy page if data is thin. | Keep only with meaningful module state or explicit data-gap surface. |
| `/macro/economy` | Primary category leaf | Economy metrics are long-label heavy; mobile length grows quickly. | Use nowcast-style summary and compact metric groups. |
| `/macro/economy/gdp` | Primary leaf | GDP labels/units need stable label/value separation. | Use compact macro metric rows and evidence below. |
| `/macro/economy/employment` | Primary leaf | `Payrolls`/`Claims` labels can split; many labor metrics can stack. | Use employment summary strip and compact detail list. |
| `/macro/economy/inflation` | Primary leaf | CPI/PCE labels are short but currently vulnerable to one-character wrapping. | Use non-fragmenting labels and inflation-specific summary ordering. |
| `/macro/economy/consumer` | Secondary leaf | Valuable but lower-frequency; should not add navigation noise. | Keep supported as secondary page with compact consumer summary. |
| `/macro/volatility` | Primary category leaf | `VIX` and term-structure labels can split. | Use volatility summary strip and table/list detail. |
| `/macro/volatility/vix` | Primary leaf | Short symbol labels are the clearest wrapping failure case. | Use fixed symbol zone and date/meta separation. |
| `/macro/credit` | Primary category leaf | Credit OAS labels and units can overrun generic cards. | Use credit spread summary rows and stress panel. |
| `/macro/credit/stress` | Primary leaf | Stress page needs high-density comparison rather than repeated generic cards. | Use compact stress board/table plus evidence. |

## Target Architecture

Macro UI should be organized around four explicit page kinds:

- **Overview page**: a command summary with global read, status, key driver metrics, transmission, and data health. It prioritizes first-viewport synthesis over repeating every table.
- **Index page**: a dense directory/table surface for a module family, currently `/macro/assets`.
- **Leaf page**: a module-local analytical page with key metrics, market board, module judgment, transmission, evidence, provenance, and data health.
- **Matrix page**: a high-density analytical matrix with paired summaries and coverage, currently `/macro/assets/correlation`.

The implementation should introduce a small macro UI component set with clear responsibilities:

- **Macro page scaffold** owns page-kind layout, width rules, panel placement, and responsive bands.
- **Macro header/status strip** owns breadcrumb, title, question, status, as-of, and history/data-health readiness.
- **Metric strip and metric tile/list components** own all KPI presentation and label/value wrapping rules.
- **Panel component** owns the common section frame, section header, optional meta badge, and body spacing.
- **Responsive table frame** owns bounded horizontal scroll, sticky row/column context, overflow affordance, and table density.
- **Evidence, transmission, data health, and source panels** render module payload records without owning route-level layout.

Route wrappers may select a page kind and pass module data, but they should not duplicate layout logic or know internal component CSS. Generic leaf wrappers should remain thin. Correlation should share shell/header primitives instead of being a separate visual island.

## Conceptual Data Flow

```text
macro_module_view_v3 payload
  -> route resolves moduleId/pageKind
  -> MacroShell renders header and content frame
  -> page-kind renderer chooses overview/index/leaf/matrix composition
  -> shared macro UI primitives render metrics, panels, tables, evidence, health
```

No backend arrow changes. The only changed arrow is inside the frontend macro feature: route wrappers stop coupling directly to generic card grids and instead pass data through page-kind renderers and macro UI primitives.

## Core Models

- **MacroPageKind**: semantic route presentation class. Values: `overview`, `index`, `leaf`, `matrix`, `unsupported`.
- **MacroDensityBand**: viewport/layout class derived from container and viewport constraints. Values: `desktop`, `compactDesktop`, `tablet`, `mobile`.
- **MacroMetricDisplay**: normalized view of a metric tile. Fields: label, short label, value, unit label, observed date, quality, and optional trend. It is presentation-only and must be derived from existing module tiles or records.
- **MacroPanelRole**: semantic section role such as summary, market, judgment, transmission, evidence, source, health, matrix, coverage.
- **MacroProductTier**: route/product visibility class. Values: `primary`, `secondary`, `hiddenSupported`, `unsupported`. It governs navigation exposure and review, not backend availability.

## Interface Contracts

No public HTTP, WebSocket, CLI, or database contract changes.

The frontend contract changes are visual and semantic:

- Macro route rendering must expose stable accessible regions for overview, index, leaf, and matrix page kinds.
- KPI/metric components must expose readable text at all supported breakpoints.
- Table/matrix frames must keep horizontal overflow inside the component and provide accessible labels.
- Sidebar navigation remains the only full macro navigation surface.
- Hidden supported pages must never appear in primary sidebar, but direct links must render either a meaningful module page or an explicit unavailable/data-gap state.

## Acceptance Criteria

- AC1. WHEN `/macro` is loaded at `1366x720`, `1096x690`, and `1920x1080`, THEN the first viewport SHALL use the available content width intentionally, with no orphan 7-column summary card and no large empty right-side region.
- AC2. WHEN any macro page with KPI metrics is loaded at `390x844`, `430x932`, `834x1194`, `1096x690`, `1366x720`, or `1920x1080`, THEN labels such as `SPX`, `VIX`, `CPI`, `SOFR`, `DXY`, `HY OAS`, `Payrolls`, and `Claims` SHALL remain readable and SHALL NOT split into one-character vertical fragments.
- AC3. WHEN `/macro/assets/equities`, `/macro/rates/yield-curve`, `/macro/liquidity`, `/macro/economy`, `/macro/volatility`, and `/macro/credit/stress` are loaded on mobile, THEN the page SHALL have no body-level horizontal overflow, no text overlap, and no clipped controls.
- AC4. WHEN a table or matrix is wider than its mobile container, THEN horizontal scrolling SHALL be bounded to that table/matrix frame and the frame SHALL provide visual and accessible context for scrolling.
- AC5. WHEN `/macro/assets/correlation` is loaded, THEN it SHALL share the macro shell/header grammar and responsive page contract while preserving the correlation matrix workflow.
- AC6. WHEN all 32 currently supported macro route paths are swept in browser automation at the required viewports, THEN there SHALL be zero console errors, zero unintended alert states, zero body-level horizontal overflow cases, and zero primary-sidebar occurrences of hidden labels `拍卖`, `FOMC 声明`, `美联储讲话`, `Dashboard`, and `CDS 代理`.
- AC7. WHEN frontend architecture tests run, THEN macro CSS SHALL remain owner-scoped, cascade-layered, and below the side-effect CSS budget; no retired CSS buckets or compatibility selectors SHALL be introduced.
- AC8. WHEN component tests render overview, asset index, leaf, matrix, hidden-supported, loading, empty, stale, and error states, THEN each state SHALL use the same macro primitives and SHALL NOT duplicate route-specific layout CSS.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Component extraction changes visual behavior without improving product clarity. | High | Extract by page role and acceptance criteria, not by generic abstraction count. |
| Mobile tables become technically scrollable but still hard to understand. | Medium | Require sticky context or a visible scroll affordance for every wide table/matrix frame. |
| Overview becomes too dense and loses hierarchy. | Medium | Treat overview as first-view command summary with limited metrics, then detailed panels below. |
| Hidden supported pages remain confusing when opened directly. | Medium | Add explicit product tier semantics and direct-route unavailable/data-gap surfaces. |
| CSS split creates churn without guardrails. | Medium | Keep owner namespaces and run architecture harness; do not create generic CSS buckets. |
| Tests pass snapshots but miss real layout clipping. | High | Add browser-level viewport audit for route sweep and inspect computed overflow/label fragmentation. |

## Evolution Path

After this hard cut, the macro UI can add richer domain-specific pages without repeating layout decisions. The next plausible expansion is module-specific compact summaries for rates curve, liquidity plumbing, and economy nowcast pages. This spec should not foreclose those pages; it should provide primitives that let specialized renderers swap in dense summaries while preserving the shell, header, metric, panel, and table contracts.

## Alternatives Considered

- **Patch current CSS only** — rejected because the main defects come from mixed page semantics and buried components, not one bad media query. CSS-only fixes would keep overview, leaf, matrix, and index pages coupled to one generic grid.
- **Create one bespoke page per module** — rejected because it would improve screenshots quickly but would duplicate layout logic across macro modules and make future responsive work harder.
- **Return to page-local macro navigation/tabs** — rejected because navigation was intentionally moved to shell/sidebar and repeated page navigation was one of the original product problems.
- **Change backend payloads to solve layout** — rejected because the current defects are presentation and composition defects; backend facts are sufficient for this hard cut.

## Boundaries

| Class | Behaviour |
|-------|-----------|
| Always | Use existing `macro_module_view_v3` payloads; preserve shell/sidebar navigation; verify all supported macro routes across required viewports; keep CSS owner-scoped. |
| Ask first | Removing addressability of hidden supported routes; changing module labels; changing backend fields; changing non-macro shell behavior beyond measured macro needs. |
| Never | Add compatibility rendering for retired macro tabs, recompute macro scores in frontend, create global CSS buckets, or solve layout by hiding data that should remain visible. |
