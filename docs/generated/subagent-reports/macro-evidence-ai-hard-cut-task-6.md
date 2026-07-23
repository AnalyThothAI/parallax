# Subagent Report - 2026-07-23-macro-evidence-ai-hard-cut / Task 6

Mode: write-allowed

## Findings

- The legacy Macro workbench, sixteen-module route/model registry, universal
  renderer, asset-correlation adapter, duplicated rates/assets UI, charts,
  tables, breadcrumb/subnav ownership, and their feature CSS/tests were
  hard-deleted.
- The supported UI is exactly six explicit routes: `/macro`,
  `/macro/cross-asset`, `/macro/rates-inflation`, `/macro/growth-labor`,
  `/macro/liquidity-funding`, and `/macro/credit`. `/macro/overview` and the
  previous nested paths render the ordinary application `404 Not Found`
  surface and issue no Macro API request.
- Six explicit page components consume six strict generated-schema page
  contracts. The independent typed series hook consumes
  `/api/macro/series`; the frontend therefore references exactly the approved
  six page reads plus one series read.
- The navigation is one flat six-item list. The application shell imports its
  descriptors through `@features/macro/shell`, so page exports remain lazy.
- The shared page/evidence primitives render projection version, fact
  watermark, market cutoff, computed time, horizon, conclusion, drivers,
  confirmations, contradictions, upgrade/invalidation, actual rule hits,
  freshness, evidence references, units, changes, legal change windows,
  observation dates, frequency, source, series key, samples, quality,
  criticality, claim effect, derivations, and reasons without hover-only
  disclosure. Named unavailable capabilities are visibly `未评估 · 不计分`.
- Page-specific structures preserve cutoff-aligned 20/60-session returns and
  correlations, nominal-curve level versus move, real yields, breakevens,
  funding corridor, release-aware inflation, growth/labor leading and lagging
  layers, secured/unsecured funding, the non-causal net-liquidity accounting
  proxy, and all six Credit layers. Credit stage and direction are separate.
- Evidence concepts now use trader-readable Chinese labels while retaining
  exact English concept keys, ticker/provider names, units, and formulae as
  secondary evidence.
- News list/detail, Search, Token Case, Ops, Cockpit status, and Notifications
  are fact-only. Dead News normalizers/models/tests, SearchAgentBrief,
  NarrativeAdmission, model-execution status, and AI-labelled surfaces were
  removed.
- Token Radar now validates
  `token_factor_snapshot_v4_transparent_factors`, accepts exactly
  `social_heat`, `social_propagation`, and `timing_risk`, and shows transparent
  propagation score/informative-post/duplicate-share facts. It has no
  semantic-catalyst or narrative-admission fallback.
- Current `web/src` has zero matches for the retired product-AI vocabulary
  used by the Task 6 residual gate.

## Scope Adherence

Owned scope: pass

Conflict set: pass

The parent delegated the Task 6 frontend hard cut and explicitly expanded the
fact-only consumer boundary to the directly coupled Cockpit, Ops,
Notifications, Live Radar, shared model, E2E mock, architecture-test, and
fixture files needed to remove the retired contracts end to end. No backend
Python, migration, operator configuration, canonical documentation, generated
OpenAPI source, or active SDD status was edited by this lane. This report is
the only generated artifact added.

## Changed Files

Registered Task 6 touch-set paths changed:

- `web/src/features/macro/**`
- `web/src/features/news/**`
- `web/src/features/search/**`
- `web/src/features/token-case/**`
- `web/src/lib/**`
- `web/src/routes/**`
- `web/tests/component/features/macro/**`
- `web/tests/routes/**`

The parent-expanded end-to-end deletion also required directly coupled
Cockpit, Live Radar, Ops, shared-model, architecture-test, fixture, and E2E
files. Those additions are described in Scope Adherence and Findings because
the active task registry still records the narrower pre-delegation touch set.

## Required Reading Evidence

Task classification: Frontend CSS Or Route Shell; Macro Evidence Snapshot Or
Freshness.

- `AGENTS.md`: material-fact truth, current read-model identity, hard-cut,
  frontend CSS ownership, and real-runtime boundaries.
- `docs/agent-playbook/task-reading-matrix.md`: frontend route/CSS ownership,
  diagnostic commands, and the Macro evidence context boundary.
- `docs/FRONTEND.md`: lazy route/shell entrypoints, owner CSS, feature
  namespace, 500-line budget, responsive and architecture gates.
- Active `spec.md`, `plan.md`, `tasks.md`, and `verification.md`: approved six
  UI routes, seven API reads, complete evidence contract, fact-only AI
  consumers, old-route 404 behavior, and 1920/1366/834/390 acceptance.
- Current generated OpenAPI TypeScript was the only Macro response-type source;
  no parallel handwritten compatibility response contract was introduced.

## Verification Evidence

Exact registered Task 6 gate:

```text
$ cd web && npm run lint && npm run typecheck && npm run test -- --run tests/component/features/macro tests/routes/macro.route.test.tsx
13 architecture files / 75 architecture tests passed
2 targeted files / 20 targeted tests passed
exit code: 0
```

Final frontend architecture and static gates:

```text
$ cd web && npm run lint
13 architecture files passed
75 architecture tests passed
exit code: 0

$ cd web && npm run typecheck
exit code: 0

$ cd web && npm run format:check
All matched files use Prettier code style
exit code: 0
```

Final full component/unit/route suite:

```text
$ cd web && npm run test -- --run --reporter=dot
76 test files passed
313 tests passed
exit code: 0
```

Production build:

```text
$ cd web && npm run build
1936 modules transformed
build completed
exit code: 0
```

Required Macro browser viewports:

```text
$ cd web && npm run test:e2e -- tests/e2e/golden-paths/macro-evidence-pages.spec.ts \
    --project=desktop-1920 --project=desktop-1366 \
    --project=tablet-834 --project=mobile-390
12 tests passed
exit code: 0
```

The Macro browser gate rendered every page at all four widths, checked the
flat six-link nav and complete visible evidence sections, verified Rates and
Credit semantics, asserted no document/nested horizontal overflow, and proved
the retired overview path is not routed through a fallback.

Final complete Playwright matrix:

```text
$ cd web && npm run test:e2e
74 tests passed
61 project-inapplicable tests skipped by explicit desktop/mobile/tablet guards
exit code: 0
```

Production frontend residual and whitespace gates:

```text
$ rg <retired product-AI vocabulary> web/src
0 matches
exit code: 1 (expected no-match result)

$ git diff --check -- web
exit code: 0
```

## Remaining Risks

- These frontend browser gates use deterministic HTTP fixtures. Parent
  acceptance still must exercise the six pages against the real API process
  and one non-empty PostgreSQL-published snapshot after the irreversible
  migration.
- Task 6 does not claim the repository-wide migration, Docker/runtime,
  generated-contract synchronization, `make check-all`, or final independent
  specification review; those remain parent/Task 8 completion evidence.
