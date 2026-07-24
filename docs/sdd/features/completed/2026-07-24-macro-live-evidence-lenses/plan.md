# Plan — Macro Live Evidence Lenses and DeepAgents Research Separation

**Status**: Verified
**Date**: 2026-07-24
**Owning spec**: `docs/sdd/features/completed/2026-07-24-macro-live-evidence-lenses/spec.md`
**Worktree**: `.worktrees/deepagents-macro-hard-cut/`
**Branch**: `codex/deepagents-macro-hard-cut`
**Approved by**: user and GitHub Issue #8
**Approved at**: 2026-07-24

## Analyze Gate

| Check | Result |
|-------|--------|
| Material owner | Pass: `macro_observations` already retains concept, source, series, value, unit, quality, source clock, raw provenance, and ingestion clock. |
| Research owner | Pass: `CompletedSessionMacro` and `/api/macro/research` already provide the approved immutable DeepAgents publication. |
| Removed product seam | Pass: the current worktree deleted the six old page routes together with their deterministic projection/rule stack. |
| Reusable metadata | Pass: the prior 108-concept manifest contains the approved page/section/unit ordering but must be reduced to presentation-only fields. |
| New storage need | Pass: none; read-time material-fact queries and bounded arithmetic satisfy the live product. |
| Public seam | Pass: one parameterized `/api/macro/evidence/{view_id}` can serve dashboard and all detail routes without restoring compatibility endpoints. |
| Frontend seam | Pass: one feature-owned hook, route-state window, shared dashboard/detail components, and local CSS match the frontend architecture. |
| Deployment | Pass: the existing Compose runtime and migration chain can deliver the forward fix without a rollback or backup prerequisite. |

## Pre-flight

- [x] Worktree exists at `.worktrees/deepagents-macro-hard-cut/` and `git branch --show-current` matches `codex/deepagents-macro-hard-cut`.
- [x] Existing uncommitted DeepAgents hard-cut changes are the implementation base and will be preserved.
- [x] Main checkout untracked screenshots are outside the target branch and will not be removed or overwritten.

## Design

1. Add a presentation-only catalog with page, section, order, Chinese label,
   unit formatting, summary membership, and default history window.
2. Add repository queries for latest selected source/series rows, bounded
   history, and uncatalogued latest facts directly from `macro_observations`.
3. Build one pure live-evidence assembler that creates row-local missing facts
   and named descriptive calculations without semantic states.
4. Add exact API schemas and one parameterized read route.
5. Add dashboard/detail routes, feature-owned hooks, local query state,
   searchable tables, simple charts, refresh status, and a compact research
   card.
6. Keep the existing research page component and move it to
   `/macro/research`.
7. Regenerate contracts and align canonical documentation.
8. Validate, commit, merge, build, migrate, and smoke-test the exact image.

## Rollout and recovery

This is a forward-only product correction. The migration chain from the
DeepAgents hard cut remains authoritative; no deleted projection or judgment
tables return. Runtime recovery consists of fixing the read query, API, or UI
while `macro_observations` and immutable research publications remain intact.

## Acceptance test commands

- AC1: `cd web && npm test -- --run tests/routes/macro.route.test.tsx`
- AC2: `cd web && npm test -- --run tests/routes/macro.route.test.tsx tests/component/features/macro/MacroLiveEvidencePage.test.tsx`
- AC3: `uv run pytest tests/unit/test_api_macro_contract.py -q`
- AC4: `uv run pytest tests/unit/test_api_macro_contract.py tests/unit/domains/macro_intel/test_macro_live_evidence.py -q`
- AC5: `uv run pytest tests/unit/domains/macro_intel/test_macro_live_catalog.py tests/unit/domains/macro_intel/test_macro_live_evidence.py -q`
- AC6: `cd web && npm test -- --run tests/routes/macro.route.test.tsx`
- AC7: `uv run pytest tests/unit/domains/macro_intel/test_macro_live_evidence.py tests/unit/test_api_macro_contract.py -q`
- AC8: `uv run pytest tests/architecture/test_product_ai_hard_delete.py tests/integration/test_deepagents_macro_research_migration.py -q`
- AC9: `uv run pytest tests/unit/integrations/model_execution/test_macro_research_deepagent.py tests/integration/test_macro_research_publication.py -q`
- AC10: `cd web && npm run test:e2e -- tests/e2e/golden-paths/macro-live-evidence.spec.ts --project=desktop-1920 --project=desktop-1366 --project=tablet-834 --project=mobile-390`
- AC11: `make regen-contract && make docs-generated`
- AC12: `uv run python scripts/check_sdd_gate.py --feature 2026-07-24-macro-live-evidence-lenses --gate verify`

## Verification commands

```text
uv run python scripts/validate_sdd_artifacts.py
uv run python scripts/regen_sdd_work_index.py --check
uv run pytest tests/unit/domains/macro_intel tests/unit/test_api_macro_contract.py tests/architecture/test_product_ai_hard_delete.py -q
uv run pytest tests/integration/test_deepagents_macro_research_migration.py tests/integration/test_macro_research_publication.py -q
cd web && npm test -- --run tests/routes/macro.route.test.tsx tests/component/features/macro/MacroLiveEvidencePage.test.tsx tests/architecture
cd web && npm run lint
cd web && npm run typecheck
cd web && npm run build
cd web && npm run test:e2e -- tests/e2e/golden-paths/macro-live-evidence.spec.ts --project=desktop-1920 --project=desktop-1366 --project=tablet-834 --project=mobile-390
make regen-contract
make docs-generated
git diff --check
```
