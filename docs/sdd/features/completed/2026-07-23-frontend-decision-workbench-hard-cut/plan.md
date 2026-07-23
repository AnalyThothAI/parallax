# Plan — Parallax Frontend Decision Workbench Hard Cut

**Status**: Verified
**Superseded by**: N/A
**Date**: 2026-07-23
**Owning spec**: `docs/sdd/features/completed/2026-07-23-frontend-decision-workbench-hard-cut/spec.md`
**Worktree**: `.worktrees/frontend-decision-workbench-hard-cut/`
**Branch**: `codex/frontend-decision-workbench-hard-cut`
**Approved by**: delegated user goal and GitHub Issue #5
**Approved at**: 2026-07-23

## Pre-flight

- [x] Spec is approved.
- [x] Worktree exists at `.worktrees/frontend-decision-workbench-hard-cut/` and `git branch --show-current` matches `codex/frontend-decision-workbench-hard-cut`.
- [x] Baseline `uv run ruff check .` passes.
- [x] Baseline targeted Python contract suite passes: 241 Macro domain/API tests.
- [x] Baseline frontend typecheck and production build pass.
- [x] Frontend lint, complete Vitest, typecheck, production build, and four-project Playwright suite pass after the baseline path/timing defects were removed.

Known-failing baseline tests (none expected):

- None. The obsolete absolute-path scanner was replaced with ownership assertions, and the complete frontend suite is green.

## File-level edits

### Macro deterministic decision projection

- `src/parallax/domains/macro_intel/_constants.py`
  - Replace `macro_evidence_v1` with the new decision-contract projection version.
- `src/parallax/domains/macro_intel/services/macro_decision_map.py`
  - Add the pure deep module that evaluates current/prior completed-session evidence and returns the strict shock summary, ordered eight-lane map, key changes, local degradation, and category confidence.
- `src/parallax/domains/macro_intel/services/macro_evidence_snapshot.py`
  - Build current and fifth-prior cutoff inputs with one calendar policy, attach the complete decision summary to Overview, normalize trustworthy catalyst instants, and retain the full audit payload.
- `src/parallax/domains/macro_intel/services/macro_dominant_shock.py`
  - Separate no-dominant-shock from insufficient evidence and expose stable evidence used by the decision summary.
- `src/parallax/domains/macro_intel/runtime/macro_view_projection_worker.py`
  - Continue using the same writer and bounded observations while publishing the new projection version.
- `src/parallax/domains/macro_intel/repositories/macro_intel_repository.py`
  - Keep one current snapshot and versioned series/publication reads; remove assumptions that accept the retired projection version.

### Projection-version forward cut

- `src/parallax/platform/db/alembic/versions/20260723_0192_macro_decision_workbench_hard_cut.py`
  - Irreversibly remove only retired v1 derived projection/publication/series rows, preserve `macro_observations`, and enqueue the existing v2 projection target so reads fail closed until rebuilt.
- `tests/integration/test_macro_decision_workbench_migration.py`
  - Upgrade a non-empty predecessor database, prove material-fact preservation, retired current-state removal, rebuild enqueue, and explicit irreversible downgrade.

### Strict HTTP and generated contracts

- `src/parallax/app/surfaces/api/schemas.py`
  - Add exact shock state, lane, change, confidence, key-change, local-degradation, and normalized catalyst fields; change the projection literal without compatibility fields.
- `src/parallax/app/surfaces/api/routes_macro.py`
  - Preserve the seven URLs and direct persisted reads.
- `docs/generated/openapi.json`
  - Regenerate from the actual application.
- `web/src/lib/types/openapi.ts`
  - Regenerate from OpenAPI; do not handwrite a parallel Macro contract.
- `web/tests/fixtures/macroFixture.ts`
  - Replace the evidence-first Overview fixture with named decision scenarios.

### Parallax design system and shared components

- `web/src/styles/tokens.css`, `web/src/styles/base.css`
  - Replace the historical palette/typography/spacing with the sole Parallax token, density, focus, state, and chart grammar.
- `web/src/shared/ui/workbench/**`
  - Add/rename the owned primitives for shell, page frame, section, metric, data row/table, status, chart frame, catalyst, and audit drawer.
- `web/src/shared/ui/case-file/**`
  - Rename Obsidian-branded case components and CSS selectors to Parallax case-workbench names.
- `web/src/shared/ui/obsidian.tsx`, `web/src/shared/ui/obsidian.css`, `web/src/shared/ui/obsidianRecords.css`, `web/src/shared/ui/obsidianLanguage.ts`
  - Remove after all consumers use the new primitives; no forwarding exports.
- `web/src/shared/ui/PageState.tsx`, `web/src/shared/ui/PageState.css`
  - Standardize loading, empty, error, unavailable, and degraded variants with compact layouts.

### Global shell and navigation

- `web/src/features/cockpit/ui/AppSidebar.tsx`, `AppSidebar.css`
  - Apply Parallax brand, five primary research destinations, and Search context without nested Macro or browser Ops routes.
- `web/src/features/cockpit/ui/CockpitTopbar.tsx`, `CockpitTopbar.css`
  - Keep search; replace permanent normal-status chrome with one anomaly-only, non-interactive status indicator.
- `web/src/features/cockpit/ui/CockpitShell.tsx`, `SearchShell.tsx`, `cockpitShell.css`, `cockpitShellContract.css`, `appNavigation.ts`
  - Apply the new shell/density/breakpoint contract while preserving route scroll and drawer ownership.

### Four page archetypes

- `web/src/features/live/ui/**`, `web/src/features/stocks/ui/**`, `web/src/features/news/**`
  - Convert scan surfaces to compact table/list-first desktop layouts and labelled mobile rows without changing feature data contracts.
- `web/src/features/search/ui/**`, `web/src/features/token-case/ui/**`, renamed shared case components
  - Convert Search, Token Case, and News Detail to one object-centric case-workbench grammar.
- `web/src/features/watchlist/ui/**`
  - Convert Watchlist to a change/anomaly-first monitoring surface and remove the large decorative hero.
- Feature-owned CSS in `web/src/features/{live,stocks,news,search,token-case,watchlist}/**`
  - Use the feature namespace and shared tokens; delete retired visual selectors and duplicate primitives.

### Macro cockpit and drilldowns

- `web/src/features/macro/model/macroTypes.ts`, `macroDisplay.ts`, `macroNavigation.ts`
  - Map strict generated enums to Chinese labels and route context only; remove business inference and flat six-link navigation data.
- `web/src/features/macro/api/useMacroPageQueries.ts`, `useMacroSeriesQuery.ts`
  - Keep feature-owned typed reads; Overview remains one request and domain charts use the series route.
- `web/src/features/macro/ui/MacroPageFrame.tsx`, `MacroSeriesPanel.tsx`, `pages/MacroOverviewPage.tsx`
  - Add the explicit Overview decision cockpit, progressive audit disclosure,
    and separate-unit chart frame.
- `web/src/features/macro/ui/pages/*.tsx`
  - Rebuild Overview and five domain pages around the approved reading order and bespoke content.
- `web/src/features/macro/ui/*.css`
  - Replace the evidence-first shell/card wall with owner-namespaced workbench layouts at the four target viewport contracts.
- `web/src/features/macro/ui/MacroPageShell.tsx`, `MacroEvidenceBlocks.tsx`, and replaced CSS
  - Delete after consumers move; no wrapper or alias remains.

### Frontend tests and visual evidence

- `web/tests/routes/macro.route.test.tsx`, `web/tests/component/features/macro/**`
  - Assert strict scenarios, one Overview request, first-screen content, drilldowns, local degradation, audit drawer, and no trade/LLM output.
- `web/tests/routes/**`, `web/tests/component/features/{cockpit,live,stocks,news,search,token-case,watchlist}/**`
  - Update product behavior for the four archetypes without freezing private markup.
- `web/tests/architecture/macroDecisionHardCut.test.ts`, `frontendDocContract.test.ts`, `designSystemHardCut.test.ts`, `cssResponsiveContract.test.ts`, `dataRouterArchitecture.test.ts`
  - Delete or rewrite source-text/old-brand assertions as durable ownership, one-style, no-inference, and route behavior gates.
- `web/tests/e2e/golden-paths/macro-evidence-pages.spec.ts`, `mobile-route-cold-load.spec.ts`
  - Replace evidence-default-visible expectations with cockpit/readability/audit behavior.
- `web/tests/e2e/golden-paths/frontend-workbench.spec.ts`
  - Add all-route 1920/1366/834/390 overflow/reachability/first-screen checks and bounded screenshots with fixed clock, timezone, locale, fonts, and animation.
- `web/playwright.config.ts`
  - Keep exactly the four approved visual projects and deterministic screenshot settings.

### Backend tests

- `tests/unit/domains/macro_intel/test_macro_decision_map.py`
  - Golden pure scenarios for eight lanes, shock states, confidence, five-session comparison, local degradation, and prohibited outputs.
- `tests/unit/domains/macro_intel/test_macro_evidence_snapshot.py`
  - Update the exact six-document contract and catalyst normalization.
- `tests/unit/test_api_macro_contract.py`
  - Assert strict new Overview/API/OpenAPI shape, seven URLs, direct persisted reads, old version rejection, and no prohibited fields.
- `tests/integration/domains/macro_intel/test_macro_evidence_projection.py`
  - Extend the real PostgreSQL writer/read seam for v2 atomicity, six shared documents, and zero-write replay.
- `tests/golden/test_macro_decision_corpus.py`
  - Run curated projection scenarios across the public document contract.

### Canonical documentation

- `docs/FRONTEND.md`
  - Become the authority for the Parallax design system, component inventory, four archetypes, shell, responsive, accessibility, and visual regression.
- `docs/ARCHITECTURE.md`, `docs/CONTRACTS.md`, `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/DEVELOPMENT.md`
  - Describe the v2 Overview decision contract, unchanged single-writer truth, two acceptance seams, progressive audit disclosure, and hard-cut test policy.
- `docs/generated/sdd-work-index.md`
  - Regenerate after the active feature is created and after completion.

## PR breakdown

1. **One product PR — frontend decision workbench hard cut**: contains the projection-version cut, strict backend contract, generated types, complete frontend replacement, tests, visual baselines, and canonical docs. Internal commits may remain reviewable, but no slice is deployed or supported independently.

## Analyze Gate

| Check | Result |
|-------|--------|
| Spec goals map to file-level edits. | Pass: every goal maps to Macro projection/API, design system/shell, page archetype, tests, or docs sections above. |
| Plan preserves canonical architecture boundaries. | Pass: one existing writer/store, direct persisted reads, feature API ownership, Router/Query/socket and CSS ownership remain. |
| Compatibility code or old files are not retained. | Pass: v1 projection rows, old brand/primitives/selectors/tests and evidence-first wrappers are removed after consumer migration. |
| Parallel touch/conflict sets are explicit. | Pass: no subagents are delegated; the single worktree owns the entire change and existing worktrees are not touched. |

## Rollout order

1. Add failing domain/API/browser contract tests.
2. Implement and validate the deterministic v2 Overview projection.
3. Add the irreversible derived-state-only forward migration and non-empty upgrade test.
4. Regenerate OpenAPI and TypeScript types.
5. Hard-cut the design system, shell, page archetypes, Macro cockpit, and all consumers.
6. Delete v1 visual/runtime compatibility and rewrite old tests.
7. Update canonical docs and generated records.
8. Verify the focused non-empty Macro migration/projection seam, production image build, four-viewport built-app browser, screenshots, operator runtime rebuild, and SDD gates. Do not run the repository-wide integration regression per the final user direction.
9. Ship backend, generated types, and frontend as one product image; rebuild the current projection before declaring the product ready.

## Rollback

- The migration is intentionally irreversible because it deletes only rebuildable v1 derived state. Production rollback requires restoring the pre-migration database backup and redeploying the previous product image.
- Before product readiness is exposed, a failed v2 rebuild leaves Macro fail-closed as projection unavailable; it does not fall back to v1.
- Frontend rollback is the previous whole product image, not a runtime theme flag or compatibility bundle.
- Material `macro_observations` are never deleted, so v2 can be repaired and rebuilt without provider replay.

## Acceptance test commands

- AC1: `cd web && npm run lint && npm run typecheck && npm test -- --run && npm run build`
- AC2: `cd web && npm test -- --run tests/component/features/cockpit tests/routes`
- AC3: `cd web && npm run test:e2e -- --project=desktop-1920 --project=desktop-1366`
- AC4: `uv run pytest tests/unit/domains/macro_intel/test_macro_evidence_snapshot.py -q`
- AC5: `uv run pytest tests/unit/domains/macro_intel/test_macro_evidence_snapshot.py tests/unit/test_api_macro_contract.py -q`
- AC6: `uv run pytest tests/unit/domains/macro_intel tests/integration/domains/macro_intel/test_macro_evidence_projection.py -q`
- AC7: `uv run pytest tests/unit/domains/macro_intel/test_macro_evidence_snapshot.py -q`
- AC8: `uv run pytest tests/architecture/test_product_ai_hard_delete.py tests/unit/test_api_macro_contract.py -q`
- AC9: `uv run pytest tests/integration/domains/macro_intel/test_macro_evidence_projection.py tests/integration/test_macro_decision_workbench_migration.py -q`
- AC10: `uv run pytest tests/unit/test_api_macro_contract.py -q`
- AC11: `cd web && npm test -- --run tests/routes/macro.route.test.tsx tests/component/features/macro`
- AC12: `cd web && npm test -- --run tests/routes/macro.route.test.tsx tests/component/features/macro`
- AC13: `cd web && npm test -- --run tests/component/features/macro`
- AC14: `cd web && npm run test:e2e -- --project=desktop-1920 --project=desktop-1366 --project=tablet-834 --project=mobile-390`
- AC15: `cd web && npm test -- --run tests/routes tests/component`
- AC16: `uv run pytest tests/contract/test_openapi_drift.py tests/integration/test_macro_decision_workbench_migration.py -q`
- AC17: `make docker-up && make docker-status && uv run python scripts/validate_sdd_artifacts.py && uv run python scripts/regen_sdd_work_index.py --check && uv run python scripts/check_sdd_gate.py --feature 2026-07-23-frontend-decision-workbench-hard-cut --gate verify`

## Verification

Verification evidence lives in `docs/sdd/features/completed/2026-07-23-frontend-decision-workbench-hard-cut/verification.md`. No passing claim is recorded until the cited command exits zero and its output is copied there.
