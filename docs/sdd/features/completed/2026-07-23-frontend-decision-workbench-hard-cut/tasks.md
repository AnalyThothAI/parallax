# Tasks — Parallax Frontend Decision Workbench Hard Cut

**Status**: Verified
**Superseded by**: N/A
**Owning plan**: `docs/sdd/features/completed/2026-07-23-frontend-decision-workbench-hard-cut/plan.md`
**Worktree**: `.worktrees/frontend-decision-workbench-hard-cut/`
**Branch**: `codex/frontend-decision-workbench-hard-cut`
**Approved by**: delegated user goal and GitHub Issue #5
**Approved at**: 2026-07-23

## Gate Compliance

| Gate | Evidence |
|------|----------|
| Clarify | `spec.md` includes approved `## Clarifications`. |
| Checklist | `spec.md` includes a testable `## Requirement Checklist`. |
| Analyze | `plan.md` includes a complete `## Analyze Gate`. |
| Implement | Tasks are ordered test → implementation → focused verification. |
| Verify | `verification.md` records direct command output. |

## Tasks

### Task 1 — Establish and validate the active SDD

- **File(s)**: `docs/sdd/features/completed/2026-07-23-frontend-decision-workbench-hard-cut/**`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: none
- **Touch set**: `docs/sdd/features/completed/2026-07-23-frontend-decision-workbench-hard-cut/**`, `docs/generated/sdd-work-index.md`
- **Conflict set**: `src/**`; `web/**`; `tests/**`
- **Failing test first**: `tests/unit/test_validate_sdd_artifacts.py::test_verified_feature_accepts_relevant_commands_without_repository_wide_gate` — the SDD validator and clarify/checklist/analyze/implement gates reject missing or contradictory artifacts.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Implementation**: Create the four approved artifacts from Issue #5, record baseline evidence, regenerate the work index, and repair every lifecycle gate before product edits.
- **Verification**: `uv run pytest tests/unit/test_validate_sdd_artifacts.py -q`
- **Review owner**: parent
- **Factory lane**: Spec/plan
- **Deterministic constraints**: exactly four artifacts, no more than 40 tasks, one approved worktree and no implementation before gates.
- **On-demand context**: Issue #5, WORKFLOW, templates, FRONTEND, ARCHITECTURE, CONTRACTS, TESTING, and the Macro domain map.
- **Kill/defer criteria**: repair any contradictory scope or invalid gate before continuing.
- **Eval/repair signal**: validator and gate output.
- **Status**: [x]

### Task 2 — Test and implement the deterministic Macro decision document

- **File(s)**: `tests/unit/domains/macro_intel/**`, `tests/golden/**`, `src/parallax/domains/macro_intel/services/**`
- **Owner**: parent
- **Depends on**: Task 1
- **Touch set**: `tests/unit/domains/macro_intel/**`, `tests/golden/**`, `src/parallax/domains/macro_intel/services/**`
- **Conflict set**: `src/parallax/domains/macro_intel/repositories/**`; `src/parallax/app/surfaces/api/**`; `web/**`
- **Failing test first**: `tests/unit/domains/macro_intel/test_macro_evidence_snapshot.py::test_overview_exposes_fixed_decision_map` — asserts exact eight lanes, distinct shock states, five-session comparison, categorical confidence, local degradation, catalysts, and prohibited-output absence.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Implementation**: Add one pure decision-map module, evaluate current and fifth-prior completed-session cutoffs with the same rules, and attach the complete decision summary to Overview.
- **Verification**: `uv run pytest tests/unit/domains/macro_intel tests/unit/test_api_macro_contract.py -q`
- **Review owner**: parent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: existing facts only, no future values, no hidden continuous score, probability, trade, portfolio, or LLM field.
- **On-demand context**: concept manifest, completed-session calendar, current domain rule modules, and Issue #5.
- **Kill/defer criteria**: fail a lane closed when its evidence cannot support a state; never invent a provider fact.
- **Eval/repair signal**: lane order/state, shock-state, calendar, and confidence scenario failures.
- **Status**: [x]

### Task 3 — Test and implement the v2 projection/API hard cut

- **File(s)**: `src/parallax/domains/macro_intel/_constants.py`, `src/parallax/domains/macro_intel/runtime/**`, `src/parallax/domains/macro_intel/repositories/**`, `src/parallax/platform/db/alembic/versions/**`, `src/parallax/app/surfaces/api/schemas.py`, `src/parallax/app/surfaces/api/routes_macro.py`, `tests/integration/domains/macro_intel/**`, `tests/integration/test_macro_evidence_ai_hard_cut_migration.py`, `tests/unit/test_api_macro_contract.py`
- **Owner**: parent
- **Depends on**: Task 2
- **Touch set**: `src/parallax/domains/macro_intel/_constants.py`, `src/parallax/domains/macro_intel/runtime/**`, `src/parallax/domains/macro_intel/repositories/**`, `src/parallax/platform/db/alembic/versions/**`, `src/parallax/app/surfaces/api/schemas.py`, `src/parallax/app/surfaces/api/routes_macro.py`, `tests/integration/domains/macro_intel/**`, `tests/integration/test_macro_evidence_ai_hard_cut_migration.py`, `tests/unit/test_api_macro_contract.py`
- **Conflict set**: `web/**`; `docs/generated/**`; coordinate with 2026-07-22-backend-kiss-deep-audit for the Macro domain, API surfaces, tests, and generated SDD index
- **Failing test first**: `tests/integration/domains/macro_intel/test_macro_evidence_projection.py::test_projection_publishes_v2_decision_document_atomically` — proves real PostgreSQL facts, one current six-document snapshot, direct HTTP read, and unchanged zero-write replay.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Implementation**: Bump the projection contract, add exact Pydantic fields, preserve seven direct reads, and add an irreversible derived-state-only forward migration that preserves material facts and enqueues the existing writer.
- **Verification**: `uv run pytest tests/integration/domains/macro_intel tests/integration/test_macro_evidence_ai_hard_cut_migration.py tests/integration/test_macro_decision_workbench_migration.py tests/unit/test_api_macro_contract.py -q`
- **Review owner**: parent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: one writer/key, `extra=forbid`, no new table/worker/provider, no v1 fallback or alias, fail closed until rebuilt.
- **On-demand context**: revision 0191, repository SQL, non-empty migration fixtures, API exact-schema conventions.
- **Kill/defer criteria**: stop if exact predecessor inventory or material-fact preservation is not proven.
- **Eval/repair signal**: migration, row preservation, serving-write count, schema, route, and provider-isolation failures.
- **Status**: [x]

### Task 4 — Regenerate strict public and frontend contracts

- **File(s)**: `docs/generated/openapi.json`, `web/src/lib/types/openapi.ts`, `web/tests/fixtures/macroFixture.ts`, `tests/contract/test_openapi_drift.py`
- **Owner**: parent
- **Depends on**: Task 3
- **Touch set**: `docs/generated/openapi.json`, `web/src/lib/types/openapi.ts`, `web/tests/fixtures/macroFixture.ts`, `tests/contract/test_openapi_drift.py`
- **Conflict set**: `src/parallax/app/surfaces/api/**`; `web/src/features/macro/**`
- **Failing test first**: `tests/contract/test_openapi_drift.py::test_openapi_document_is_current` — rejects stale v1 schemas and hand-written parallel frontend contracts.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Implementation**: Regenerate OpenAPI and TypeScript from the actual app and replace the fixture with named supported/no-shock/insufficient/local-degradation scenarios.
- **Verification**: `uv run pytest tests/contract/test_openapi_drift.py -q`
- **Review owner**: parent
- **Factory lane**: Docs/contracts
- **Deterministic constraints**: repair generators or source contracts; never patch generated output around a backend mismatch.
- **On-demand context**: OpenAPI generator, frontend type generator, and MSW fixture conventions.
- **Kill/defer criteria**: do not start Macro UI until the generated contract typechecks.
- **Eval/repair signal**: generator diff, strict-schema error, and fixture type error.
- **Status**: [x]

### Task 5 — Test and implement the Parallax design system and shell

- **File(s)**: `web/src/styles/**`, `web/src/shared/ui/**`, `web/src/features/cockpit/**`, `web/src/routes/**`, `web/tests/architecture/**`, `web/tests/component/shared/ui/**`, `web/tests/component/features/cockpit/**`, `web/tests/routes/**`
- **Owner**: parent
- **Depends on**: Task 1
- **Touch set**: `web/src/styles/**`, `web/src/shared/ui/**`, `web/src/features/cockpit/**`, `web/src/routes/**`, `web/tests/architecture/**`, `web/tests/component/shared/ui/**`, `web/tests/component/features/cockpit/**`, `web/tests/routes/**`
- **Conflict set**: `web/src/features/macro/**`; `web/src/features/live/**`; `web/src/features/news/**`; `web/src/features/search/**`; `web/src/features/stocks/**`; `web/src/features/token-case/**`; `web/src/features/watchlist/**`
- **Failing test first**: `web/tests/component/features/cockpit/ui/AppSidebar.test.tsx::renders_the_parallax_task_first_navigation` — requires Parallax brand, five primary destinations, Search, anomaly-only health, no browser Ops route, keyboard drawer, one token/component language, and no Obsidian production primitive.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Implementation**: Replace tokens, shared primitives, case components, states, brand and shell; preserve Router/Query/socket/search ownership; migrate consumers and delete old names without aliases.
- **Verification**: `cd web && npm test -- --run tests/component/features/cockpit/ui/AppSidebar.test.tsx && npm run lint && npm run typecheck`
- **Review owner**: parent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: Radix behavior, Lucide, owner CSS/cascade, 500-line budget, no visual kit, Storybook, re-export, or dual selector.
- **On-demand context**: FRONTEND, current shell/session/socket tests, and all shared-UI consumers.
- **Kill/defer criteria**: do not weaken ownership or hide failure-state visibility.
- **Eval/repair signal**: architecture, a11y, route, focus, and type failures.
- **Status**: [x]

### Task 6 — Test and hard-cut all non-Macro page archetypes

- **File(s)**: `web/src/features/live/**`, `web/src/features/stocks/**`, `web/src/features/news/**`, `web/src/features/search/**`, `web/src/features/token-case/**`, `web/src/features/watchlist/**`, `web/tests/component/features/**`, `web/tests/routes/**`
- **Owner**: parent
- **Depends on**: Task 5
- **Touch set**: `web/src/features/live/**`, `web/src/features/stocks/**`, `web/src/features/news/**`, `web/src/features/search/**`, `web/src/features/token-case/**`, `web/src/features/watchlist/**`, `web/tests/component/features/**`, `web/tests/routes/**`
- **Conflict set**: `web/src/features/macro/**`; `src/**`; `docs/**`
- **Failing test first**: `web/tests/routes/live-radar.route.test.tsx::renders_the_scan_archetype` — representative route behavior requires compact table/list scan, object-centric case, anomaly-first monitoring, shared states, labelled mobile rows, and unchanged endpoints.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Implementation**: Recompose current data through the four approved archetypes without changing business models, ranking, provider, or API ownership.
- **Verification**: `cd web && npm test -- --run tests/routes/live-radar.route.test.tsx`
- **Review owner**: parent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: table/list first on desktop, no business inference, system health and business evidence remain separate.
- **On-demand context**: current feature models, route tests, and new shared primitives.
- **Kill/defer criteria**: do not change backend semantics to simplify layout.
- **Eval/repair signal**: endpoint, state, responsive, and data-ownership failures.
- **Status**: [x]

### Task 7 — Test and implement the Macro cockpit and five drilldowns

- **File(s)**: `web/src/features/macro/**`, `web/tests/component/features/macro/**`, `web/tests/routes/macro.route.test.tsx`, `web/tests/architecture/macroDecisionHardCut.test.ts`
- **Owner**: parent
- **Depends on**: Task 4, Task 5
- **Touch set**: `web/src/features/macro/**`, `web/tests/component/features/macro/**`, `web/tests/routes/macro.route.test.tsx`, `web/tests/architecture/macroDecisionHardCut.test.ts`
- **Conflict set**: `src/**`; `web/src/features/cockpit/**`; `web/src/shared/ui/**`
- **Failing test first**: `web/tests/routes/macro.route.test.tsx::renders_the_decision_cockpit_from_one_overview_read` — asserts the three-band first screen, exact lanes, shock-state split, local degradation, collapsed audit, catalyst/invalidation, one request, five explicit drilldowns, charts, and no duplicate nav/trade/LLM output.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Implementation**: Render Overview directly from v2, add accessible progressive audit, rebuild five bespoke domain pages around the common reading order, and delete the evidence-first shell/navigation without a universal renderer.
- **Verification**: `cd web && npm test -- --run tests/routes/macro.route.test.tsx tests/architecture/macroDecisionHardCut.test.ts`
- **Review owner**: parent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: static label/format mapping only, one Overview request, no scoring/sorting/fan-out, full evidence accessible, no unexplained dual axis.
- **On-demand context**: generated v2 types, named fixtures, series contract, domain-specific evidence pages.
- **Kill/defer criteria**: a missing typed field is a backend defect, not a frontend inference opportunity.
- **Eval/repair signal**: contract, request-count, first-screen, audit, chart, and a11y failures.
- **Status**: [x]

### Task 8 — Prove four-viewport built-app behavior and remove the replaced contract

- **File(s)**: `web/playwright.config.ts`, `web/tests/e2e/**`, `web/tests/architecture/**`, `web/src/**`
- **Owner**: parent
- **Depends on**: Task 6, Task 7
- **Touch set**: `web/playwright.config.ts`, `web/tests/e2e/**`, `web/tests/architecture/**`, `web/src/**`
- **Conflict set**: `src/**`; `tests/**`; `docs/**`
- **Failing test first**: `web/tests/e2e/golden-paths/frontend-workbench.spec.ts::frontend_workbench` — all stable routes at 1920/1366/834/390 require first-screen focus, no overflow, reachability, keyboard audit, stable requests, and bounded deterministic screenshots.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Implementation**: Replace old evidence-default browser expectations, freeze visual inputs, add representative archetype and six-Macro screenshots, then delete old brand, selectors, wrappers, tests, and compatibility references after consumers are gone.
- **Verification**: `cd web && npm run test:e2e -- tests/e2e/golden-paths/frontend-workbench.spec.ts --project=desktop-1920 --project=desktop-1366 --project=tablet-834 --project=mobile-390`
- **Review owner**: parent
- **Factory lane**: Harness/tests
- **Deterministic constraints**: no fifth visual viewport, no loose screenshot threshold, no baseline before nondeterminism is fixed, no historical-record rewrite.
- **On-demand context**: mock API, layout helpers, all stable routes, current screenshot policy.
- **Kill/defer criteria**: repair unexpected requests, timing, fonts, clock, or animation before accepting a baseline.
- **Eval/repair signal**: screenshot diff, overflow, inaccessible last item, unexpected API, and residual-reference scan.
- **Status**: [x]

### Task 9 — Align docs and complete requirement-by-requirement verification

- **File(s)**: `docs/FRONTEND.md`, `docs/ARCHITECTURE.md`, `docs/CONTRACTS.md`, `docs/TESTING.md`, `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/generated/**`, `docs/sdd/features/completed/2026-07-23-frontend-decision-workbench-hard-cut/**`
- **Owner**: parent
- **Depends on**: Task 3, Task 4, Task 5, Task 6, Task 7, Task 8
- **Touch set**: `docs/FRONTEND.md`, `docs/ARCHITECTURE.md`, `docs/CONTRACTS.md`, `docs/TESTING.md`, `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/generated/**`, `docs/sdd/features/completed/2026-07-23-frontend-decision-workbench-hard-cut/**`
- **Conflict set**: `src/parallax/domains/macro_intel/services/**`; `web/src/**`; `web/tests/**`
- **Failing test first**: `tests/unit/test_validate_sdd_artifacts.py::test_verified_feature_rejects_cited_command_without_successful_evidence` — rejects current v1 contract claims, generated drift, incomplete SDD evidence, and unrecorded acceptance commands without invoking the waived broad integration lane.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Implementation**: Rewrite canonical current truth, regenerate all source-derived artifacts, run the focused PostgreSQL/generated/frontend/browser gates, build and start the product image against the operator database, audit every AC and residual, repair defects, record exact evidence, and move the feature to completed only after the verify gate passes.
- **Verification**: `uv run pytest tests/unit/test_validate_sdd_artifacts.py -q`
- **Review owner**: parent
- **Factory lane**: Final integration
- **Deterministic constraints**: no completion from intent, narrow tests, static scans, or manual screenshots alone; the actual image, migration, worker rebuild, API, and browser must agree.
- **On-demand context**: full spec/plan/tasks, final diff, runtime/browser receipts, generator output.
- **Kill/defer criteria**: keep the goal active until every requirement has direct current-state proof.
- **Eval/repair signal**: failed AC, omitted lane, residual compatibility, unverified migration/runtime, or SDD gate failure.
- **Status**: [x]
