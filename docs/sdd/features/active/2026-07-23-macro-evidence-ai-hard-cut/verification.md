# Verification — Evidence-first Macro Intel And Product-AI Hard Cut

**Status**: Review
**Superseded by**: N/A
**Date**: 2026-07-23
**Owning spec**: `docs/sdd/features/active/2026-07-23-macro-evidence-ai-hard-cut/spec.md`
**Owning plan**: `docs/sdd/features/active/2026-07-23-macro-evidence-ai-hard-cut/plan.md`
**Branch**: `codex/macro-evidence-ai-hard-cut`
**Worktree**: `.worktrees/macro-evidence-ai-hard-cut/`
**Approved by**: delegated goal
**Approved at**: 2026-07-23
**Diff**: full worktree diff from fixed base `11a7fab52d9` was independently reviewed.

## Spec compliance

| Acceptance criterion | Status | Evidence |
|----------------------|--------|----------|
| AC1 - Six pages and seven reads; old surfaces 404. | Pass | Latest isolated Docker runtime returned 200 for six page reads and the series read; retired APIs returned 404. |
| AC2 - One atomic six-document snapshot. | Pass | Projection integration and Docker reads proved one shared projection/version/watermark tuple. |
| AC3 - Unchanged replay writes zero rows. | Pass | Non-empty projection integration replay passed with zero serving writes. |
| AC4 - Complete judgment contract without score/confidence. | Pass | Task 3's accepted report and domain/API/browser gates verify the pure judgment contract. |
| AC5 - Critical fail-closed and optional degraded. | Pass | Rule-matrix and Docker page freshness states distinguish critical insufficiency from optional degradation. |
| AC6 - Cross-asset aligned returns/correlations. | Pass | Common-interval 20/60-session calculations passed domain and projection coverage. |
| AC7 - Rates/inflation skeleton and units. | Pass | Nominal/real/breakeven/funding/inflation separation and fail-closed display helpers passed backend and frontend checks. |
| AC8 - Growth/labor and liquidity/funding skeletons. | Pass | Leading/lagging layers and the non-causal net-liquidity accounting proxy passed domain and page checks. |
| AC9 - Six-layer Credit and quadrant/stage. | Pass | Current-state golden and aligned rating-tail calculations passed; Docker served the typed Credit document. |
| AC10 - Missing capabilities not assessed/not scored. | Pass | Manifest-backed unavailable capabilities remain explicit and do not create synthetic scores. |
| AC11 - Product AI absent; facts/notification retained. | Pass | Runtime/schema/API/frontend hard-delete guards, migration tests, and independent re-audit passed. |
| AC12 - Dormant LLM library, no runtime consumer. | Pass | AST/import behavior proves provider-neutral primitives remain independently importable with no production composition. |
| AC13 - Non-empty irreversible migration. | Pass | Revision 0191 preserved raw facts, archived retired queue evidence, failed closed on running delivery, and passed non-empty migration tests. |
| AC14 - Four responsive viewports. | Pass | Six Macro pages passed Playwright at 1920/1366/834/390 without whole-page overflow. |
| AC15 - Official seven-day catalysts only. | Pass | Official URL/timezone/window bounds and malformed-catalyst fail-closed behavior passed. |
| AC16 - Generated/full/runtime/independent completion. | In Progress | Generated contracts, isolated Docker, and independent P0/P1/P2 re-audit passed. The user stopped final integration-heavy `make check-all` on 2026-07-23, so no full-gate completion claim is made. |

Deviations from spec (with reason and user-approved date if any):

- None approved.

Deviations from plan (with reason):

- None recorded.

## Verification commands

No successful final `make check-all` transcript is claimed. The user stopped the
integration-heavy run on 2026-07-23 after the static/unit/frontend lanes passed.

## Coverage

| metric | value | threshold | status |
|--------|-------|-----------|--------|
| line | Not measured | >= 80% | In Progress |
| branch | Not measured | project gate | In Progress |

## Skipped tests

No final run-above skip count is recorded until a successful `make check-all` exists.

## E2E golden path

- [x] `/readyz` returned 200 from the isolated Docker stack.
- [x] Macro writer published one six-document row visible to the API process.
- [x] Seven macro API reads returned one shared projection version/watermark.
- [x] Old macro routes returned ordinary not-found.
- [x] Product-AI workers/status/contracts were absent and watched-account notification remained functional.
- [x] Six browser pages passed at 1920/1366/834/390 without whole-page overflow.
- [ ] Test containers/processes cleaned up.

## Completion gate

Not run by explicit user direction on 2026-07-23. The feature remains active in
`Review`; this record does not claim repository full-gate verification.

## Other commands run

Completed task evidence already produced during implementation:

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

$ make check-all
SDD/static/frontend gates passed; 2579 Python tests passed with provider drift enabled.
The user stopped the run during the PostgreSQL integration lane.
exit code: 130
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
- Final `make check-all`, zero-skip accounting, and completion-gate evidence
  were explicitly stopped by the user; this Review record does not promote them
  to successful verification.

## Follow-ups

- None. Out-of-scope future capabilities require new specs.
