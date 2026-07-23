# Verification — Evidence-first Macro Intel And Product-AI Hard Cut

**Status**: Verified
**Superseded by**: N/A
**Date**: 2026-07-23
**Owning spec**: `docs/sdd/features/completed/2026-07-23-macro-evidence-ai-hard-cut/spec.md`
**Owning plan**: `docs/sdd/features/completed/2026-07-23-macro-evidence-ai-hard-cut/plan.md`
**Branch**: `codex/macro-evidence-ai-hard-cut`
**Worktree**: `.worktrees/macro-evidence-ai-hard-cut/`
**Approved by**: delegated goal
**Approved at**: 2026-07-23
**Diff**: full worktree diff from fixed base `11a7fab52d9` was independently reviewed.

## Spec compliance

| Acceptance criterion | Status | Evidence |
|----------------------|--------|----------|
| AC1 - Six pages and seven reads; old surfaces 404. | Pass | `uv run pytest tests/unit/test_api_macro_contract.py tests/unit/test_api_news_contract.py tests/integration/test_api_http.py tests/contract/test_openapi_drift.py tests/unit/test_settings.py tests/unit/test_worker_factories.py -q` exited 0; isolated Docker reads also returned the expected 200/404 split. |
| AC2 - One atomic six-document snapshot. | Pass | `uv run pytest tests/integration/domains/macro_intel/test_macro_evidence_projection.py tests/integration/test_macro_evidence_ai_hard_cut_migration.py tests/unit/test_macro_evidence_ai_hard_cut_migration_contract.py -q` exited 0. |
| AC3 - Unchanged replay writes zero rows. | Pass | `uv run pytest tests/integration/domains/macro_intel/test_macro_evidence_projection.py tests/integration/test_macro_evidence_ai_hard_cut_migration.py tests/unit/test_macro_evidence_ai_hard_cut_migration_contract.py -q` exited 0. |
| AC4 - Complete judgment contract without score/confidence. | Pass | `uv run pytest tests/unit/domains/macro_intel -q` exited 0. |
| AC5 - Critical fail-closed and optional degraded. | Pass | `uv run pytest tests/unit/domains/macro_intel -q` exited 0. |
| AC6 - Cross-asset aligned returns/correlations. | Pass | `uv run pytest tests/unit/domains/macro_intel -q` exited 0. |
| AC7 - Rates/inflation skeleton and units. | Pass | `uv run pytest tests/unit/domains/macro_intel -q` exited 0. |
| AC8 - Growth/labor and liquidity/funding skeletons. | Pass | `uv run pytest tests/unit/domains/macro_intel -q` exited 0. |
| AC9 - Six-layer Credit and quadrant/stage. | Pass | `uv run pytest tests/unit/domains/macro_intel -q` exited 0. |
| AC10 - Missing capabilities not assessed/not scored. | Pass | `uv run pytest tests/unit/domains/macro_intel -q` exited 0. |
| AC11 - Product AI absent; facts/notification retained. | Pass | `uv run pytest tests/architecture/test_product_ai_hard_delete.py tests/unit/test_api_macro_contract.py -q` and `uv run pytest tests/unit/domains/news_intel tests/unit/domains/token_intel tests/unit/domains/notifications tests/unit/integrations/model_execution -q` exited 0. |
| AC12 - Dormant LLM library, no runtime consumer. | Pass | `uv run pytest tests/unit/domains/news_intel tests/unit/domains/token_intel tests/unit/domains/notifications tests/unit/integrations/model_execution -q` exited 0. |
| AC13 - Non-empty irreversible migration. | Pass | `uv run pytest tests/integration/domains/macro_intel/test_macro_evidence_projection.py tests/integration/test_macro_evidence_ai_hard_cut_migration.py tests/unit/test_macro_evidence_ai_hard_cut_migration_contract.py -q` exited 0. |
| AC14 - Four responsive viewports. | Pass | `cd web && npm run lint && npm run typecheck && npm run test -- --run tests/component/features/macro tests/routes/macro.route.test.tsx` exited 0; the recorded Playwright receipt covered 1920/1366/834/390. |
| AC15 - Official seven-day catalysts only. | Pass | `uv run pytest tests/unit/domains/macro_intel -q` exited 0. |
| AC16 - Generated/runtime/independent completion. | Pass | `uv run pytest tests/integration/test_docs_generated.py tests/contract/test_openapi_drift.py tests/architecture/test_product_ai_hard_delete.py -q && uv run python scripts/regen_sdd_work_index.py --check` exited 0; isolated Docker and the independent P0/P1/P2 re-audit also passed. |

Deviations from spec (with reason and user-approved date if any):

- None approved.

Deviations from plan (with reason):

- None recorded.

## Verification commands

Completed task evidence produced during implementation:

```text
$ uv run pytest tests/architecture/test_product_ai_hard_delete.py tests/unit/test_api_macro_contract.py -q
14 passed in 3.81s
exit code: 0

$ uv run pytest tests/unit/domains/news_intel tests/unit/domains/token_intel tests/unit/domains/notifications tests/unit/integrations/model_execution -q
468 passed in 4.43s
exit code: 0

$ uv run pytest tests/unit/domains/news_intel/test_news_page_projection.py -q
7 passed in 0.04s
exit code: 0

$ uv run pytest tests/unit/domains/macro_intel -q
203 passed in 0.32s
exit code: 0

$ uv run pytest tests/unit/domains/macro_intel/test_macro_evidence_snapshot.py -q
12 passed in 0.03s
exit code: 0

$ uv run pytest tests/integration/domains/macro_intel/test_macro_evidence_projection.py tests/integration/test_macro_evidence_ai_hard_cut_migration.py tests/unit/test_macro_evidence_ai_hard_cut_migration_contract.py -q
10 passed
exit code: 0

$ uv run pytest tests/unit/test_api_macro_contract.py tests/unit/test_api_news_contract.py tests/integration/test_api_http.py tests/contract/test_openapi_drift.py tests/unit/test_settings.py tests/unit/test_worker_factories.py -q
134 passed in 318.43s
exit code: 0

$ cd web && npm run lint && npm run typecheck && npm run test -- --run tests/component/features/macro tests/routes/macro.route.test.tsx
13 architecture files / 75 architecture tests passed
2 targeted files / 20 targeted tests passed
exit code: 0

$ uv run pytest tests/integration/test_docs_generated.py tests/contract/test_openapi_drift.py tests/architecture/test_product_ai_hard_delete.py -q && uv run python scripts/regen_sdd_work_index.py --check
13 passed
SDD work index is current.
exit code: 0

$ uv run pytest tests/architecture/test_product_ai_hard_delete.py tests/unit/test_macro_evidence_ai_hard_cut_migration_contract.py -q
9 passed in 3.99s
exit code: 0

```

## Diff summary

Files changed (grouped by package):

- `src/parallax/domains/macro_intel/**`: fixed evidence manifest, six-page
  snapshot/rules, stable projection, and strict persisted reads.
- `src/parallax/app/**`, `src/parallax/domains/{news_intel,token_intel,notifications}/**`,
  and `src/parallax/platform/**`: product-AI hard deletion, fact-only surviving
  paths, strict public contracts, runtime/config cleanup, and revision `0191`.
- `web/**`: six explicit Macro pages plus fact-only News, Search, Token,
  Watchlist, Ops, Cockpit, and Notification consumers.
- `tests/**`, canonical docs, and `docs/generated/**`: replacement behavior,
  migration, hard-delete, browser, generated-contract, and review evidence.

Migrations applied:

- `20260723_0191` was applied only to isolated verification databases, following
  byte-identical prerequisite revisions `20260722_0189` and `20260722_0190`.
  It has not been applied to the operator database.

Schema or contract changes that consumers must be aware of:

- Old macro module/AI contracts are intentionally removed without compatibility.

## Risks observed

- The independent re-audit found no P0/P1/P2 issue after repair, but deliberately
  did not connect to PostgreSQL. Root-owned migration evidence covers that seam.
- Integration, runtime, browser, and independent-review evidence came from
  separate focused receipts rather than one repository-wide wrapper.

## Follow-ups

- None. Out-of-scope future capabilities require new specs.
