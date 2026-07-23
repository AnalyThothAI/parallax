# Spec — Parallax Frontend Decision Workbench Hard Cut

**Status**: Verified
**Superseded by**: N/A
**Date**: 2026-07-23
**Owner**: Codex `/root`
**Approved by**: delegated user goal and GitHub Issue #5
**Approved at**: 2026-07-23
**Verified at**: 2026-07-23
**Related**: `https://github.com/AnalyThothAI/parallax/issues/5`, `docs/sdd/features/completed/2026-07-23-macro-evidence-ai-hard-cut/spec.md`, `docs/FRONTEND.md`, `docs/ARCHITECTURE.md`, `docs/CONTRACTS.md`

## Background

The current frontend preserves the intended React layer boundaries and feature-owned data hooks, but its supported visual contract still prioritizes evidence metadata over task comprehension. The shared Macro shell renders the six-route navigation and snapshot/audit metadata before the page-owned content. Its production route tests require the raw macro projection version to be visible, while the browser golden path requires all six navigation links and full evidence metadata to be expanded. These current sources are visible in [Frontend architecture](https://github.com/AnalyThothAI/parallax/blob/416f8be8bc113dd53ef266a7be1bc80ccd511762/docs/FRONTEND.md#L5-L24), [MacroPageShell](https://github.com/AnalyThothAI/parallax/blob/416f8be8bc113dd53ef266a7be1bc80ccd511762/web/src/features/macro/ui/MacroPageShell.tsx#L35-L127), [route tests](https://github.com/AnalyThothAI/parallax/blob/416f8be8bc113dd53ef266a7be1bc80ccd511762/web/tests/routes/macro.route.test.tsx#L64-L69), and [browser tests](https://github.com/AnalyThothAI/parallax/blob/416f8be8bc113dd53ef266a7be1bc80ccd511762/web/tests/e2e/golden-paths/macro-evidence-pages.spec.ts#L18-L67).

The current backend has the correct durable boundary. The Macro projection worker reads persisted compact facts, builds one snapshot, and publishes through the single repository writer. The snapshot builder returns exactly six documents with shared metadata, and the API reads each persisted document directly. However, the Overview contract exposes a dominant-shock evidence object and catalysts, not the complete fixed eight-lane decision map or the five-completed-session comparison required by Issue #5. See the current [worker](https://github.com/AnalyThothAI/parallax/blob/416f8be8bc113dd53ef266a7be1bc80ccd511762/src/parallax/domains/macro_intel/runtime/macro_view_projection_worker.py#L137-L169), [snapshot builder](https://github.com/AnalyThothAI/parallax/blob/416f8be8bc113dd53ef266a7be1bc80ccd511762/src/parallax/domains/macro_intel/services/macro_evidence_snapshot.py#L45-L260), [routes](https://github.com/AnalyThothAI/parallax/blob/416f8be8bc113dd53ef266a7be1bc80ccd511762/src/parallax/app/surfaces/api/routes_macro.py#L20-L92), and [strict schemas](https://github.com/AnalyThothAI/parallax/blob/416f8be8bc113dd53ef266a7be1bc80ccd511762/src/parallax/app/surfaces/api/schemas.py#L185-L222).

The global shell still presents historical GMGN/Obsidian brand copy and a permanent normal-state badge. Shared visual primitives and case-file components also retain Obsidian-branded names. These are current production contracts, not merely archived evidence, as shown by [AppSidebar](https://github.com/AnalyThothAI/parallax/blob/416f8be8bc113dd53ef266a7be1bc80ccd511762/web/src/features/cockpit/ui/AppSidebar.tsx#L35-L70), [shared primitives](https://github.com/AnalyThothAI/parallax/blob/416f8be8bc113dd53ef266a7be1bc80ccd511762/web/src/shared/ui/obsidian.tsx#L1-L179), and [case components](https://github.com/AnalyThothAI/parallax/blob/416f8be8bc113dd53ef266a7be1bc80ccd511762/web/src/shared/ui/case-file/TokenCaseHero.tsx#L1-L107).

## Problem

The product does not provide one coherent research hierarchy. Macro cannot answer its five primary questions in one scan, audit metadata obscures decisions, duplicated navigation competes with content, and each feature invents density and page structure independently. A frontend-only redesign would move deterministic macro inference into the browser, while a compatibility rollout would leave two design systems and two product contracts to maintain.

## Clarifications

| Question | Answer | Approved by | Approved at |
|----------|--------|-------------|-------------|
| Is this only a Macro restyle? | No. It is a one-release hard cut of the full supported frontend, including brand, shell, design system, shared components, page archetypes, and every current route. | user / Issue #5 | 2026-07-23 |
| Does the product keep two styles during migration? | No. Internal implementation may be sequenced, but the final supported tree has one Parallax design system and no compatibility aliases, wrappers, selectors, or fallback reads. | user / Issue #5 | 2026-07-23 |
| What is Macro? | A fixed, generic cross-asset risk map for the current completed US session and the next 1–4 weeks. It is not personalized. | user / Issue #5 | 2026-07-23 |
| Which lanes are fixed? | US equities, long-duration Treasuries, credit, USD, gold, oil, crypto, and market volatility. | user / Issue #5 | 2026-07-23 |
| What does a lane show? | Tailwind/neutral/headwind/insufficient evidence, strengthening/stable/weakening/insufficient evidence versus five completed sessions earlier, categorical confidence, rationale, contradiction, and invalidation. | user / Issue #5 | 2026-07-23 |
| Is “no dominant shock” a failure? | No. It is a valid state distinct from insufficient evidence. | user / Issue #5 | 2026-07-23 |
| Who computes Macro judgments? | The existing deterministic backend projection. The frontend only maps labels and formats numbers, dates, local time, and countdowns. | user / Issue #5 | 2026-07-23 |
| Is an LLM added? | No. Any future LLM interpretation requires a separate spec. | user / Issue #5 | 2026-07-23 |
| Does Macro output trades or sizing? | Never. No holdings, buy/sell instruction, position size, target price, or allocation recommendation. | user / Issue #5 | 2026-07-23 |
| Are evidence and freshness removed? | No. Normal audit data moves behind progressive disclosure; critical missing/stale/degraded evidence remains next to the affected conclusion. | user / Issue #5 | 2026-07-23 |
| Are routes or the frontend framework replaced? | No. Current URLs and React/Vite/Router/Query/WebSocket ownership remain. `/` remains Radar. | user / Issue #5 | 2026-07-23 |
| Does this supersede Issue #4? | Only its global shell, brand, Overview information budget, Macro navigation, default evidence presentation, and visual-test decisions. Its PostgreSQL truth, single writer, six-document snapshot, seven reads, deterministic no-AI/no-trade, and fail-closed evidence boundaries remain. | user / Issue #5 | 2026-07-23 |
| Is implementation authorized now? | Yes. The active goal explicitly delegates completion of the current spec. | delegated goal | 2026-07-23 |
| What is the final runtime gate? | Do not block this hard cut on the repository-wide integration regression. Keep the focused non-empty Macro migration/projection seam, then build the product image, migrate the operator database, let the real worker rebuild v2, and inspect the running API and browser. | user | 2026-07-23 |

## Requirement Checklist

| Requirement | Quality gate |
|-------------|--------------|
| One Parallax design system replaces all current visual contracts. | Architecture scan rejects old brand, Obsidian visual names, aliases, duplicate tokens, retired selectors, and parallel primitives. |
| Shell is task-first and normal health is quiet. | App route/browser tests prove five primary research destinations, Search flow, anomaly-only accessible status, no browser Ops route, and preserved route reachability. |
| Four page archetypes cover every stable route. | Built-app route matrix and visual baselines cover scan, case, decision, and monitoring surfaces. |
| Macro Overview answers the five decision questions in the first desktop screen. | 1920/1366 browser assertions and screenshot baselines prove the three-band first-screen budget. |
| Eight fixed lanes have strict deterministic semantics. | Domain golden tests assert exact lane order, direction, five-session trend, confidence, rationale, contradiction, invalidation, and local degradation. |
| No-dominant-shock and insufficient-evidence are distinct. | Domain/API/UI scenario tests cover both states independently. |
| Five-session comparison uses completed sessions without look-ahead. | Calendar-aware tests cover weekends, holidays, early close, data gaps, and insufficient history. |
| Frontend performs no Macro business inference. | Typed API and frontend ownership tests reject client-computed lane/shock/confidence/sort logic and multi-page fan-out. |
| Existing Kappa/CQRS and single-writer invariants remain. | Focused real-PostgreSQL projection/migration checks plus the rebuilt operator runtime prove one current six-document snapshot, atomic acknowledgement, public-read isolation, and v2 publication. |
| Contract changes are a hard cut. | Projection version, Pydantic, OpenAPI, generated TypeScript, fixtures, current projection rebuild, and docs move together without aliases. |
| Evidence remains auditable but visually subordinate. | Browser tests prove normal audit content is collapsed, critical gaps are adjacent, and the keyboard-accessible drawer exposes full metadata. |
| Domain pages are explicit and chart-capable. | Route/browser tests prove five bespoke pages, shared reading order, 20/60-session charts, source/unit/as-of, and no universal renderer. |
| Responsive behavior changes information priority. | 1920/1366/834/390 behavior and visual checks prove desktop density, mobile quick scan, no overflow, reachability, and no hover-only information. |
| No trade, holdings, sizing, score, probability, or LLM output enters the contract. | Backend/frontend negative contract tests and architecture scan. |
| Canonical docs and automated evidence match runtime. | Docs/OpenAPI/generated-type/SDD validators and final completion audit. |

## First principles

- PostgreSQL material facts remain the only business truth, and the current Macro read model remains one rebuildable six-document snapshot with one writer (`docs/ARCHITECTURE.md:109-131`).
- Product judgments have one owner. Existing routes consume feature-owned typed API hooks and may not own server reads or business inference (`docs/FRONTEND.md:49-53`).
- A hard cut removes the replaced contract. Public contract changes update behavior, tests, generated types, canonical docs, and delete the old name/path rather than adding an alias (`docs/CONTRACTS.md:225-234`).

## Goals

- G1. Deliver one dark, restrained, Chinese-first Parallax research workbench across every stable route with no historical brand or dual visual contract.
- G2. Make `/macro` the sole decision cockpit whose first desktop screen exposes one shock state, exactly eight lanes, up to three key changes, the nearest catalyst, and one core invalidation.
- G3. Publish all Macro decision fields from the existing deterministic single-writer projection under a new strict projection contract.
- G4. Preserve current material facts, compact series, six-document current identity, seven public reads, route URLs, React architecture, and WebSocket ownership.
- G5. Provide explicit domain drilldowns with 20/60-session context while hiding normal audit detail behind accessible progressive disclosure.
- G6. Prove the product at 1920, 1366, 834, and 390 through focused projection/migration checks, built-app browser behavior, bounded screenshot baselines, and an actual Docker image/runtime rebuild.
- G7. Remove old brand, Obsidian visual primitives/names, duplicated Macro navigation, evidence-first page shell, source-text tests, and compatibility code.

## Non-goals

- N1. No new provider, material fact, table, materialized view, queue, worker, WebSocket topic, or second Macro writer.
- N2. No personalized portfolio, holdings analysis, buy/sell instruction, position size, target price, allocation, or execution.
- N3. No LLM-generated judgment, explanation, summary, ranking, or confidence.
- N4. No intraday Macro, point-in-time replay, backtest, long-range forecast, or new historical data product.
- N5. No business-ranking or fact-model change for Radar, Stocks, News, Search, Token Case, or Watchlist.
- N6. No React/Vite/Router/Query/WebSocket replacement, URL rename, second runtime, visual kit, Storybook, theme switcher, or customizable dashboard.
- N7. No production deployment, credential change, or live-provider debugging as part of this code change.

## Target architecture

```text
existing providers
  -> macro_observations material facts
  -> existing dirty targets + compact series
  -> existing single Macro projection writer
  -> one current snapshot with six strict documents
       overview = decision summary + eight-lane map + audit payload
       five domains = explicit evidence documents
  -> six page reads + one series read
  -> feature-owned React hooks
  -> one Parallax shell + one design system
  -> four explicit page archetypes
```

The Overview is self-contained. The browser does not request all five domain documents to reconstruct the decision map.

## Conceptual data flow

```text
persisted facts -> deterministic rules at current and prior completed-session cutoffs
                -> typed Overview decision document
                -> Macro cockpit

persisted compact series -> typed series read -> five explicit domain chart pages
```

The only new semantic arrow is the deterministic projection of current and five-session-prior lane states into the existing Overview document. No new store, writer, or provider is introduced.

## Core models

- **Shock state**: `dominant`, `no_dominant_shock`, or `insufficient_evidence`; it includes candidate, concise Chinese summary, categorical confidence, change state, rationale, confirmations, contradictions, and evidence references.
- **Risk lane**: one of eight fixed ordered identities. It includes direction (`tailwind`, `neutral`, `headwind`, `insufficient_evidence`), five-session trend (`strengthening`, `stable`, `weakening`, `insufficient_evidence`), categorical confidence (`high`, `medium`, `low`, `insufficient_evidence`), concise summary, drivers, contradiction, invalidation, evidence refs, and degradation reason.
- **Key change**: a bounded backend-ranked item describing what changed between the two completed-session cutoffs and which lane/domain it affects. Overview contains at most three.
- **Catalyst**: an official persisted event. Parsed events include a normalized instant; unparsed events retain official date/time text and never produce a fabricated countdown.
- **Audit bundle**: shared snapshot metadata, conclusion/rule data, freshness, full evidence, unavailable capabilities, formulas, and references. It is part of the API but normally collapsed in the UI.
- **Page archetype**: scan, case, decision cockpit, or monitoring. It determines information hierarchy, not business data ownership.
- **Design token contract**: the sole semantic palette, typography, spacing, density, radius, elevation, focus, motion, breakpoint, state, number/unit, and chart grammar.

## Interface contracts

- UI routes remain `/`, `/stocks`, `/news`, `/news/items/:id`, `/macro`, the five current `/macro/*` drilldowns, `/watchlist`, `/search`, and `/token/:targetType/:targetId`; operational diagnosis remains on API/CLI surfaces and there is no browser Ops route.
- Macro HTTP remains exactly six page reads and one series read. Overview changes in place under a new projection version; old fields and version are not accepted as a parallel response.
- Every page read remains strict and persisted. Missing projection returns the existing unavailable response; unknown paths return ordinary `404`.
- Overview returns the complete fixed risk map and decision summary. Domain reads retain their evidence-specific strict shapes. Series remains bounded and explicit.
- The frontend may format but may not derive business state. Critical local gaps remain visible next to the affected result; normal audit data is available through an accessible drawer.
- Catalyst display uses browser-local time first and official timezone second only when the backend provides a trustworthy normalized instant.

## Acceptance criteria

- AC1. WHEN the supported frontend is built THEN the system SHALL contain one Parallax brand, one design token contract, one component language, and no old visual compatibility path or Obsidian-branded production primitive.
- AC2. WHEN a user navigates the shell THEN the system SHALL prioritize Radar, Stocks, News, Macro, and Watchlist, preserve Search and all stable URLs, and show system health globally only when an anomaly exists as an accessible topbar status without adding a browser Ops route.
- AC3. WHEN `/macro` renders at 1920 or 1366 THEN its first screen SHALL contain exactly the decision header, eight ordered lanes, and the bounded changes/catalyst/invalidation band without duplicate Macro navigation, expanded audit metadata, giant hero, or empty card wall.
- AC4. WHEN the projection has no established dominant shock but adequate evidence THEN Overview SHALL return and render `no_dominant_shock`; WHEN critical evidence is inadequate THEN it SHALL return and render `insufficient_evidence`.
- AC5. WHEN Overview is projected THEN it SHALL contain exactly the eight fixed lanes once each, with typed direction, five-session trend, categorical confidence, summary, driver, contradiction, invalidation, evidence references, and local degradation.
- AC6. WHEN a five-session trend is produced THEN current and comparison states SHALL use the same versioned deterministic rules at the latest completed US session and its fifth prior completed session, including correct holiday/early-close handling and no future values.
- AC7. WHEN one lane lacks critical evidence THEN only that lane and dependent summary SHALL fail closed while unrelated valid lanes remain available.
- AC8. WHEN any Macro public response or UI is inspected THEN it SHALL contain no holdings, trade instruction, size, target, allocation, probability, continuous confidence score, or LLM-derived field.
- AC9. WHEN identical persisted facts are projected twice THEN the system SHALL keep one `current` six-document snapshot, acknowledge durable work atomically, and write zero serving rows on the unchanged replay.
- AC10. WHEN a Macro page is requested THEN the API SHALL read the persisted document without provider calls, worker execution, wide fact scans, cross-page fan-out, or frontend business inference.
- AC11. WHEN a user opens normal Macro content THEN audit metadata SHALL be collapsed; WHEN a critical freshness/evidence problem affects a result THEN the problem SHALL be shown adjacent to that result; WHEN the audit drawer opens THEN complete evidence/rule/formula/version data SHALL be keyboard accessible.
- AC12. WHEN a user opens any of the five Macro drilldowns THEN the page SHALL follow current judgment → key changes → core charts → confirmations/contradictions → catalysts/invalidation while retaining a bespoke domain layout and 20/60-session context.
- AC13. WHEN complete charts render THEN axes, unit, legend, source, and as-of SHALL be explicit and unrelated units SHALL not be presented as an unexplained dual-axis relationship.
- AC14. WHEN stable routes render at 1920, 1366, 834, and 390 THEN desktop SHALL provide comparison density, tablet/mobile SHALL provide quick-scan priority, tables SHALL become labelled stacked rows where necessary, and no material content SHALL overflow, overlap, become unreachable, or require hover.
- AC15. WHEN loading, empty, error, unavailable, or degraded states occur THEN the system SHALL use the shared state language and preserve unaffected valid content.
- AC16. WHEN the contract hard cut lands THEN projection version, rebuild/migration behavior, Pydantic, OpenAPI, generated frontend types, fixtures, tests, and canonical docs SHALL agree with no alias or dual read.
- AC17. WHEN completion is claimed THEN focused Macro migration/projection checks, generated contract, frontend lint/type/build/tests, built-app four-viewport behavior, bounded screenshots, actual Docker image/migration/worker/API/browser receipts, SDD gates, and requirement-by-requirement evidence SHALL all be recorded and successful.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| A categorical confidence hides a continuous score. | High | Build categories directly from explicit evidence coverage/confirmation/contradiction rules and reject score/probability fields. |
| Five-session comparison leaks future data or uses natural days. | Critical | Reuse the completed-session calendar at both cutoffs and test weekends, holidays, early closes, and insufficient history. |
| `no_dominant_shock` is conflated with missing evidence. | High | Separate enum states across domain, API, fixtures, UI, and golden scenarios. |
| Progressive disclosure hides a critical limitation. | High | Local degradation is a required lane field and a browser acceptance assertion. |
| Overview becomes a frontend aggregate over five APIs. | High | Store complete decision summary in Overview and assert one Overview request. |
| Projection-version hard cut serves stale v1 JSON to a v2 schema. | High | Forward migration/rebuild state deletes only the old current projection, enqueues the existing writer, and fails closed until v2 is published. |
| Full frontend cut leaves historical names or selectors. | High | Negative architecture gate over production/current docs/tests plus consumer-first removal. |
| Screenshot maintenance expands without bound. | Medium | Baseline scan, case, and monitoring representatives plus all six decision-oriented Macro routes at four fixed viewports; state permutations use semantic tests. |
| Normal health becomes invisible during failure. | Medium | One anomaly-only, accessible topbar status preserves failure visibility while diagnosis remains on API/CLI surfaces. |
| A wide visual change is mistaken for completion after narrow tests. | Critical | Two top-level seams plus generated contracts, all-route matrix, real PostgreSQL, and final completion audit. |

## Evolution path

Future LLM interpretation, point-in-time macro history, personalized portfolio context, or additional evidence providers require separate specs. The typed decision model should remain explainable enough that a future model can consume it as evidence without becoming the source of truth. New page archetypes or primitives must extend the single Parallax design contract rather than add a parallel theme or renderer.

## Alternatives considered

- **Frontend-only inference** — rejected because it creates a second business-rule owner, cross-page fan-out, and untestable drift from the persisted projection.
- **Incremental dual-theme migration** — rejected because the user explicitly requires a final one-style hard cut and the repository would retain compatibility selectors and duplicate component semantics.
- **A third-party visual kit or Storybook** — rejected because Radix, Lucide, TanStack Table, and Lightweight Charts already cover behavior; another kit and catalog would create an extra maintenance surface.
- **A universal page renderer** — rejected because the five Macro domains and five product archetypes share reading grammar but require different information structures.
- **A new Macro table or worker** — rejected because the existing single current JSON snapshot can own the new Overview fields without changing material truth or writer ownership.

## Boundaries

| Class | Behaviour |
|-------|-----------|
| Always | Preserve facts, stable URLs, one Macro writer, six documents, seven reads, strict types, local degradation, accessibility, and one final design contract. |
| Ask first | Production deployment, operator database migration, credential/config changes, or any expansion into new providers, LLMs, personalized holdings, or trade execution. |
| Never | Dual styles/contracts, frontend Macro inference, hidden continuous scores, fabricated catalyst times, buy/sell or sizing output, second writer, or compatibility aliases. |
