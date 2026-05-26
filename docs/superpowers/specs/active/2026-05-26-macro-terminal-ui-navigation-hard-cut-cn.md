# Spec — Macro Terminal UI Navigation Hard-Cut

**Status**: Draft
**Date**: 2026-05-26
**Owner**: Codex
**Related**:
- Plan: `docs/superpowers/plans/active/2026-05-26-macro-terminal-ui-navigation-hard-cut-plan-cn.md`
- Prior macro terminal spec: `docs/superpowers/specs/active/2026-05-25-macro-terminal-hard-cut-spec-cn.md`
- Frontend rules: `docs/FRONTEND.md`
- Macro domain architecture: `src/gmgn_twitter_intel/domains/macro_intel/ARCHITECTURE.md`
- Local benchmark snapshot: `timsun-assets-snapshot.md`

## Background

The current Macro Terminal has the correct deterministic data lane, but the UI and module view contract still mix navigation, global macro regime, module facts, and data-health concerns.

- The backend module view builder projects every module through one generic payload path. It returns tiles, chart, tables, read, evidence, provenance, data gaps, and related routes from `build_macro_module_view` in `src/gmgn_twitter_intel/domains/macro_intel/services/macro_module_views.py:22`.
- Non-overview module reads currently reuse the global scenario/regime from `snapshot.scenario_json`, so every module can inherit the same global macro headline instead of answering the module's own question. See `_read` in `src/gmgn_twitter_intel/domains/macro_intel/services/macro_module_views.py:385`.
- Non-overview evidence currently reuses global scenario confirmations, contradictions, watch triggers, and invalidations. See `_evidence` in `src/gmgn_twitter_intel/domains/macro_intel/services/macro_module_views.py:398`.
- Module data gaps currently start with global snapshot gaps, then append feature and module gaps. This makes unrelated global gaps appear on every child page. See `_data_gaps` in `src/gmgn_twitter_intel/domains/macro_intel/services/macro_module_views.py:559`.
- The frontend Macro header renders primary and secondary macro tabs on every module page. See `MacroPageHeader` in `web/src/features/macro/ui/shell/MacroPageHeader.tsx:56`.
- The frontend route model duplicates the macro module list and tab helpers in `web/src/features/macro/model/macroRoutes.ts:1` and `web/src/features/macro/model/macroRoutes.ts:81`, while the backend catalog owns the runtime module list in `src/gmgn_twitter_intel/domains/macro_intel/services/macro_module_catalog.py:41`.
- The current page frame repeats a generic sequence of KPI strip, chart/table, data status, structure map, rule evidence, provenance, and data gaps for all modules. See `MacroModulePageFrame` in `web/src/features/macro/ui/pages/MacroModulePageFrame.tsx:72`.
- The current transmission map is derived from the same semantic record fields rather than a distinct chain contract. See `transmissionNodes` in `web/src/features/macro/ui/pages/MacroModulePageFrame.tsx:416`.
- The app shell already uses a shadcn `AppSidebar`, but the macro section only exposes three macro links: overview, assets, and correlation. See `web/src/features/cockpit/ui/appNavigation.ts:61`.
- The frontend contract says `/macro` renders deterministic Macro Intel from `/api/macro`, and the frontend must not recompute macro scoring. See `docs/FRONTEND.md`.
- The timsun benchmark snapshot shows a persistent left navigation tree and a content-first `大类资产` page made of compact asset-class sections and tables, not repeated horizontal navigation inside each child page. See `timsun-assets-snapshot.md:14` and `timsun-assets-snapshot.md:110`.

## Problem

Users experience the Macro Terminal as logically noisy because each child page repeats navigation and global macro state while the actual module question is hard to isolate. The UI looks like a dashboard template applied to many routes rather than a macro terminal with a stable directory, clear pages, and deterministic data semantics.

## First Principles

- Macro pages render persisted deterministic macro facts. They do not infer regime, score, direction, or narrative in React. This follows the Macro route rule in `docs/FRONTEND.md` and the domain rule that module pages consume the backend module view contract in `src/gmgn_twitter_intel/domains/macro_intel/ARCHITECTURE.md`.
- Navigation belongs to the shell/sidebar. Page headers may show breadcrumbs and local page state, but they must not repeat full macro navigation trees. This follows the shell navigation rule in `docs/FRONTEND.md` and the current shadcn sidebar ownership in `web/src/features/cockpit/ui/CockpitShell.tsx:40`.
- Module pages answer one module question. Global regime, global scenario evidence, and global source health belong to the overview or a data-health surface, not every leaf route.
- This is a hard cut. No legacy macro UI compatibility layer, v2/v3 adapter, fallback rendering path, duplicated route tab model, or "keep old classes hidden" code is allowed.

## Goals

- G1. Move the complete macro navigation tree into the app sidebar and mobile drawer, with three visible levels where applicable: `宏观 -> domain -> leaf`.
- G2. Remove repeated primary and secondary macro tabs from every module page.
- G3. Replace `macro_module_view_v2` with a clean hard-cut `macro_module_view_v3` contract for module pages.
- G4. Split module payload semantics into distinct fields: module read, module evidence, module transmission, module data health, provenance, and related routes.
- G5. Ensure non-overview module pages do not display global snapshot gaps, global scenario confirmations, or global regime headlines as if they were module-local facts.
- G6. Make `/macro/assets` a terminal index page with asset-class sections and compact tables inspired by the timsun snapshot, using only local persisted macro facts.
- G7. Update tests so product language, accessible region names, and assertions match the new page semantics.
- G8. Keep the frontend CSS harness compliant: owner-prefixed macro CSS, no retired global buckets, no restyling shared UI internals, no page cards nested inside cards.

## Non-goals

- N1. Do not fetch, scrape, proxy, or depend on `timsun.net` data or page code.
- N2. Do not add AI/LLM macro interpretation.
- N3. Do not add new external macro providers.
- N4. Do not fix macrodata freshness, SRF history, FRED coverage, or worker scheduling in this UI plan.
- N5. Do not redesign Token Radar, News, Earnings, Watchlist, Ops, or Search.
- N6. Do not keep compatibility code for old macro module payload keys, old tab helpers, or old region names.

## Target Architecture

The target Macro Terminal has four clear layers.

1. **Shell navigation layer**
   - `AppSidebar` renders the full macro tree under the existing `Intel -> 宏观` parent.
   - Desktop users see the tree in the sidebar. Tablet and mobile users see the same tree in the existing sidebar drawer.
   - Macro pages do not render full macro navigation tabs. They show breadcrumb, page title, module question, status, and optional sibling context only when it directly helps the current page.

2. **Backend macro module contract**
   - `macro_module_view_v3` is the only module page contract.
   - The backend catalog remains the authority for supported module ids and route paths.
   - Module views return module-local data structures:
     - `module_read`: answer/state fields derived from the module's concepts and chart readiness.
     - `module_evidence`: module-local confirmations, constraints, watch triggers, and invalidations derived from concept availability, chart status, module gap codes, and module-specific source state.
     - `transmission`: deterministic chain nodes that describe source facts -> module signal -> macro implication. Overview may use global `chain_json`; leaf modules do not reuse global scenario text.
     - `data_health`: grouped health buckets for module gaps, chart gaps, global health references, and future integrations.
     - `section_boards`: optional index-page content blocks for pages such as `/macro/assets`.
   - Overview may surface global regime, global scenario, and global data gaps because it is the global macro page.

3. **Frontend macro page layer**
   - `/macro` renders a global terminal overview.
   - `/macro/assets` renders an asset-class index page with compact sections and links to leaf pages.
   - Leaf pages render one module question, one primary market board, module-local evidence, a real transmission chain, data provenance, and module-local data health.
   - Unsupported macro routes do not silently normalize to `/macro`.

4. **CSS and visual layer**
   - First pass is semantic and structural.
   - Visual polish happens after contract and page meaning are correct.
   - Macro feature CSS remains under `web/src/features/macro/ui/**` and uses macro-owned selectors.

## Conceptual Data Flow

```text
macro_observations / macro_view_snapshots
  -> macro module catalog
  -> macro_module_view_v3 builder
  -> /api/macro/modules/{module_id}
  -> useMacroModuleQuery
  -> MacroShell header without nav tabs
  -> overview / index / leaf page renderer
```

Navigation flow:

```text
macro module catalog
  -> frontend macro navigation tree
  -> AppSidebar / mobile drawer
  -> route parser
  -> MacroWorkbenchRoute
```

The navigation flow may duplicate static route labels in frontend source for shell rendering, but it must be one frontend tree, not separate primary/secondary tab helpers plus sidebar children. The backend remains the runtime validation authority for module ids.

## Core Models

- `MacroNavigationNode`
  - `id`: stable route node id, such as `macro.assets.equities`.
  - `label`: displayed nav label.
  - `href`: route href.
  - `module_id`: optional macro module id for module routes.
  - `children`: nested nodes.
  - Invariant: every module node points at a backend-supported module id.

- `MacroModuleViewV3`
  - `snapshot`: module id, route path, title, subtitle, question, section, status, as-of, source snapshot id, projection version.
  - `tiles`: module concept tiles.
  - `primary_chart`: primary deterministic chart spec and series metadata.
  - `tables`: module tables.
  - `module_read`: module-local answer fields.
  - `module_evidence`: module-local evidence groups.
  - `transmission`: ordered chain nodes.
  - `data_health`: grouped data-health buckets.
  - `provenance`: source rows for module concepts.
  - `related_routes`: nearby routes.
  - `section_boards`: optional index page sections.

- `MacroDataHealth`
  - `summary_status`: `ok | partial | missing`.
  - `module_gaps`: gaps caused by required/optional concepts for the current module.
  - `chart_gaps`: gaps that block chart/table readiness.
  - `global_gaps`: global snapshot gaps, shown only on overview or as a compact reference link on leaf pages.
  - `future_integration_gaps`: known integrations not yet connected, such as options GEX.

- `MacroTransmissionNode`
  - `label`: node label.
  - `value`: observed value or state.
  - `kind`: `source | signal | implication | risk`.
  - `status`: `ok | partial | missing`.
  - Invariant: nodes must not be generated by reformatting the same `module_read` fields.

## Interface Contracts

- `GET /api/macro/modules/{module_id}`
  - Returns only `macro_module_view_v3`.
  - Unsupported module ids return the existing `unsupported_macro_module` error.
  - No legacy `macro_module_view_v2` fallback.

- `GET /api/macro`
  - Continues to return global snapshot data for overview-level surfaces.
  - It remains the only place where global `scenario`, global `chain`, global `data_gaps`, and global `scorecard` are first-class page facts.

- Frontend macro route parser
  - Parses macro routes from the single frontend macro navigation tree.
  - Unsupported paths surface an explicit unsupported-route state instead of rendering overview.

- App sidebar
  - Renders `宏观` as a collapsible tree with domain and leaf links.
  - It closes the mobile drawer on navigation using the existing sidebar behavior.

## Acceptance Criteria

- AC1. WHEN a user opens `/macro/assets/equities`, THEN the page SHALL not render `宏观主模块` or `宏观模块` horizontal tab navigation.
- AC2. WHEN a user opens `/macro/assets/equities`, THEN the app sidebar SHALL expose `宏观 -> 大类资产 -> 美股` and mark only the current leaf as current.
- AC3. WHEN a non-overview module has a global snapshot gap unrelated to its concepts, THEN the module page SHALL not show that gap as a module-local blocker.
- AC4. WHEN a non-overview module renders its read section, THEN the headline SHALL answer the module question using module-local readiness and concept state rather than the global scenario regime.
- AC5. WHEN a non-overview module renders evidence, THEN evidence SHALL come from module concepts, chart readiness, module gap codes, and module-specific external source state.
- AC6. WHEN `/macro/assets` renders, THEN it SHALL show asset-class index sections with compact tables and leaf links, not the same generic leaf module frame.
- AC7. WHEN an unsupported `/macro/*` path is opened, THEN the app SHALL show an unsupported macro route state rather than silently rendering `/macro`.
- AC8. WHEN frontend tests run, THEN old region names such as `当前解读` and old route-tab helpers SHALL not be required by tests.
- AC9. WHEN `cd web && npm run lint`, `npm run test:architecture`, `npm run typecheck`, `npm test -- --run`, and `npm run build` run, THEN they SHALL pass.
- AC10. WHEN the UI is checked at desktop, tablet, and mobile widths, THEN the sidebar/drawer navigation SHALL remain reachable and macro content SHALL not overlap or require hidden horizontal tab scrolling.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Shell sidebar becomes too deep or visually noisy. | Medium | Use a collapsible tree under `宏观`, keep domain labels short, and test mobile drawer reachability. |
| Backend and frontend macro route lists drift. | Medium | Derive frontend route parsing, breadcrumbs, and sidebar macro links from one frontend navigation tree, and add tests comparing required ids against fixture data. Backend still rejects unsupported ids. |
| Module-local reads become fake narratives. | High | Use deterministic readiness, concept state, and chart/table status only. No frontend inference and no LLM text. |
| Removing v2 contract breaks tests broadly. | Medium | Update fixtures, type contracts, API contract tests, and component tests in the same hard cut. No adapter layer. |
| `/macro/assets` index requires data that current module view does not expose. | Medium | Build `section_boards` from existing `features_json` concept facts and catalog group definitions; do not add new providers. |
| CSS polish hides semantic issues. | Medium | Implement contract and semantic tests before visual refinement. |

## Evolution Path

After this hard cut, future work can add a dedicated macro data-health page, richer module-specific transmission rules, and operator-facing sync freshness diagnostics. This design should not foreclose a later backend-provided public catalog endpoint, but the current implementation should avoid a sidebar that depends on a successful macro API fetch.

## Alternatives Considered

- Keep current module page template and only improve styling. Rejected because it preserves the root problem: repeated navigation and mixed global/module semantics.
- Add a third horizontal menu inside macro pages. Rejected because it makes the repeated-navigation problem worse and conflicts with the terminal-style sidebar reference.
- Fetch the macro navigation tree dynamically in `AppSidebar`. Rejected for this plan because global navigation should remain available even when macro API calls fail. A backend catalog endpoint can still be added later for diagnostics or contract tests.
- Keep `macro_module_view_v2` and add optional v3 fields. Rejected because the user explicitly requested no compatibility code and the current contract semantics are the source of the confusion.

## Boundaries

| Class | Behaviour |
|-------|-----------|
| Always | Move full macro navigation into the shell sidebar/drawer. |
| Always | Remove macro header primary/secondary tabs. |
| Always | Use deterministic backend module view fields. |
| Always | Treat overview global regime differently from leaf module reads. |
| Always | Keep timsun as an information architecture reference only. |
| Ask first | Add new macro providers, worker scheduling, or source freshness workers. |
| Ask first | Split this into multiple PRs despite the single-plan request. |
| Never | Render old tabs through hidden compatibility classes. |
| Never | Keep v2/v3 adapters or fallback paths. |
| Never | Use frontend heuristics to infer macro scoring or trading narrative. |
| Never | Scrape or proxy timsun. |
