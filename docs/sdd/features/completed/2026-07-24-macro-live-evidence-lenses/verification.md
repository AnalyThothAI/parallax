# Verification — Macro Live Evidence Lenses and DeepAgents Research Separation

**Status**: Verified
**Date**: 2026-07-24
**Owning spec**: `docs/sdd/features/completed/2026-07-24-macro-live-evidence-lenses/spec.md`
**Owning plan**: `docs/sdd/features/completed/2026-07-24-macro-live-evidence-lenses/plan.md`
**Branch**: `codex/deepagents-macro-hard-cut`
**Worktree**: `.worktrees/deepagents-macro-hard-cut/`
**Approved by**: user and GitHub Issue #8
**Approved at**: 2026-07-24

## Spec compliance

| Acceptance criterion | Status | Evidence |
|----------------------|--------|----------|
| AC1 - Live dashboard and research card. | Pass | `cd web && npm test -- --run tests/routes/macro.route.test.tsx tests/component/features/macro/MacroLiveEvidencePage.test.tsx` verifies six category cards plus compact persisted research context. |
| AC2 - Six complete detail routes. | Pass | `cd web && npx playwright test tests/e2e/golden-paths/macro-live-evidence.spec.ts tests/e2e/golden-paths/macro-research.spec.ts --reporter=list` verifies all six detail routes, summaries, charts, searchable rows, and source/timing fields. |
| AC3 - Separated immutable research route. | Pass | `uv run pytest tests/unit/test_api_macro_contract.py tests/contract/test_openapi_drift.py -q` verifies `/macro/research` remains persisted-only and separate from live pages. |
| AC4 - Persisted-only API. | Pass | `uv run pytest tests/unit/test_api_macro_contract.py tests/contract/test_openapi_drift.py -q` proves zero provider/model/write execution and rejects unsupported inputs. |
| AC5 - 108 metadata concepts plus uncatalogued facts. | Pass | `uv run pytest tests/unit/domains/macro_intel/test_macro_live_catalog.py tests/unit/domains/macro_intel/test_macro_live_evidence.py -q` proves exactly 108 presentation concepts and bounded uncatalogued facts. |
| AC6 - Exact clocks and row-local availability. | Pass | `uv run pytest tests/unit/domains/macro_intel/test_macro_live_catalog.py tests/unit/domains/macro_intel/test_macro_live_evidence.py -q` preserves all clocks and missing rows independently. |
| AC7 - Transparent calculations without semantic labels. | Pass | `uv run pytest tests/architecture/test_product_ai_hard_delete.py tests/unit/test_docs_contract.py -q` verifies disclosed descriptive math and forbids deterministic semantic fields. |
| AC8 - No projection or judgment regression. | Pass | `uv run pytest tests/architecture/test_product_ai_hard_delete.py tests/unit/test_docs_contract.py -q` proves retired projection, judgment, gateway, and compatibility surfaces remain deleted. |
| AC9 - DeepAgents capability preserved. | Pass | `uv run python scripts/check_macro_research_publication.py --session-date 2026-07-23` verifies the immutable DeepAgents 0.6.12 publication, three specialists, 11 model calls, and 27 citations. |
| AC10 - Responsive and interactive browser behavior. | Pass | `cd web && npx playwright test tests/e2e/golden-paths/macro-live-evidence.spec.ts tests/e2e/golden-paths/macro-research.spec.ts --reporter=list` passes 32/32 across 1366, 1920, 834, and 390 widths. |
| AC11 - Generated contracts and docs aligned. | Pass | `make check` verifies generated contracts, frontend types, canonical docs, mirrored routers, and architecture invariants. |
| AC12 - Main merge and production image verification. | Pass | `make docker-up` built the merged feature commit `63d8537f` as image `sha256:6d7281580b36ed04e07fc25d7f46055d66a6dd08c8fe2ccacc142a22dc7106b7`; migration `20260724_0195`, readiness, authenticated APIs, eight routes, workers, publication integrity, and bounded logs passed. |

## Verification commands

- `uv run pytest tests/unit/domains/macro_intel/test_macro_live_catalog.py tests/unit/domains/macro_intel/test_macro_live_evidence.py tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py tests/unit/test_api_macro_contract.py tests/unit/test_api_openapi_exact_contracts.py tests/unit/test_docs_contract.py tests/architecture/test_product_ai_hard_delete.py tests/architecture/test_kiss_runtime_invariants.py -q` — 68 passed.
- `make regen-contract && make docs-generated` — regenerated OpenAPI, TypeScript types, DB schema, CLI help, score versions, WebSocket protocol, and SDD work index.
- `make check` — ruff, formatting, mypy over 515 source files, frontend type/lint/architecture/format, 2,429 Python unit/architecture/contract tests passed, one opt-in live provider drift test skipped, and compileall passed.
- `cd web && npm test -- --run` — 71 files / 272 tests passed.
- `cd web && npx playwright test tests/e2e/golden-paths/macro-live-evidence.spec.ts tests/e2e/golden-paths/macro-research.spec.ts --reporter=list` — 32 tests passed across all four configured viewport projects.
- `make test-integration` — 235 passed; one SDD-index assertion raced with the intentional active-to-completed documentation edit, and its exact test passed immediately after index regeneration.
- `uv run python scripts/check_macro_research_publication.py --session-date 2026-07-23` — immutable publication passed with DeepAgents 0.6.12, 11 model calls, all three specialists, and 27 verified citations.
- `make docker-up` — exact application image built, migration container exited 0, and application became healthy.
- Authenticated production API smoke — dashboard plus six live views returned 200; curated availability was 9/9, 27/31, 7/15, 19/20, 15/23, and 23/23, with missing facts retained row-locally.
- Production route smoke — `/macro`, `/macro/research`, and all six detail routes returned 200; `/macro/not-a-page` returned 404.
- `git diff --check` — passed.

```text
$ uv run python scripts/validate_sdd_artifacts.py
SDD artifact validation passed before task completion.
exit code: 0

$ uv run pytest tests/unit/domains/macro_intel/test_macro_live_catalog.py tests/unit/domains/macro_intel/test_macro_live_evidence.py -q
6 passed in 0.02s.
exit code: 0

$ uv run pytest tests/unit/test_api_macro_contract.py tests/contract/test_openapi_drift.py -q
25 passed in 2.52s.
exit code: 0

$ cd web && npm test -- --run tests/routes/macro.route.test.tsx tests/component/features/macro/MacroLiveEvidencePage.test.tsx
2 files and 13 tests passed.
exit code: 0

$ test -f web/tests/routes/macro.route.test.tsx && (cd web && npm test -- --run tests/routes/macro.route.test.tsx tests/component/features/macro/MacroLiveEvidencePage.test.tsx)
2 files and 13 tests passed.
exit code: 0

$ uv run pytest tests/architecture/test_product_ai_hard_delete.py tests/unit/test_docs_contract.py -q
6 passed in 1.04s.
exit code: 0

$ make check
Ruff/format/mypy/frontend checks passed; 2,429 tests passed and one opt-in live provider-drift test skipped; compileall passed.
exit code: 0

$ cd web && npm test -- --run
71 files and 272 tests passed.
exit code: 0

$ cd web && npx playwright test tests/e2e/golden-paths/macro-live-evidence.spec.ts tests/e2e/golden-paths/macro-research.spec.ts --reporter=list
32 tests passed across desktop-1366, desktop-1920, tablet-834, and mobile-390.
exit code: 0

$ make test-integration
235 tests passed. One SDD work-index assertion failed only because the active
feature moved while the suite was running; after regenerating the index, the
exact failed test passed.
exit code: 0 for the exact rerun

$ uv run python scripts/check_macro_research_publication.py --session-date 2026-07-23
ok=true; deepagents_version=0.6.12; model=openai/gpt-5.6-terra;
model_calls=11; specialists=evidence-analyst,cross-asset-challenger,skeptical-editor;
verified citations=27; workflow=deepagents_macro_research_v3.
exit code: 0

$ make docker-up
Application image sha256:6d7281580b36ed04e07fc25d7f46055d66a6dd08c8fe2ccacc142a22dc7106b7 built.
Migration container applied head and exited 0; application container became healthy.
exit code: 0

$ GET /readyz
composition.ok=true; db.ok=true; migration_version=20260724_0195;
expected_migration_version=20260724_0195; migration_status=ready.
HTTP status: 200

$ authenticated GET /api/macro/evidence/{view_id}?window=90d
dashboard: 36 preview metrics, 35 available, 1 missing, 1,131 history points,
50 bounded uncatalogued facts, current research link.
overview: 9 available / 9 catalogued; 17 history points.
rates-inflation: 27 available / 31 catalogued; 1,595 history points.
growth-labor: 7 available / 15 catalogued; 23 history points.
liquidity-funding: 19 available / 20 catalogued; 756 history points.
credit: 15 available / 23 catalogued; 740 history points.
cross-asset: 23 available / 23 catalogued; 1,103 history points.
All seven requests returned HTTP 200; missing facts remained row-local.
exit code: 0

$ authenticated GET /api/macro/research
state=current; session=2026-07-23; title is Chinese; 4 sections;
27 citations; 4 Agent-authored evidence gaps; 1,582 CJK characters sampled
across the title, executive summary, and sections.
HTTP status: 200

$ GET /macro /macro/research and six supported detail routes
All eight supported routes returned HTTP 200; /macro/not-a-page returned 404.
exit code: 0

$ authenticated GET /api/status
macro_sync effective_status=running and last result status=ok with
max_observed_at=2026-07-24; macro_research effective_status=running,
last_error=null, and current publication persisted.
HTTP status: 200

$ docker compose logs --tail=300 app migrate
Migration completed at head. No traceback, exception, fatal, or panic was
present. Two optional LiteLLM Bedrock/SageMaker preload warnings were present
because botocore is not installed; neither provider is used by this workflow.
exit code: 0

$ uv run python scripts/check_sdd_gate.py --feature 2026-07-24-macro-live-evidence-lenses --gate verify
verify gate passed: 2026-07-24-macro-live-evidence-lenses
exit code: 0

$ git diff --check
No whitespace errors.
exit code: 0
```

## Deviations

- The repository-wide integration suite completed with 235 passing tests and
  one documentation-index mismatch caused by moving this feature from active
  to completed while the suite was executing. The exact failed assertion passed
  after the index was regenerated; no runtime or Macro test failed.
- The opt-in live provider-drift test remains intentionally skipped by
  `make check`.
- Per the owner's explicit instruction, no database backup was created before
  the forward-only removal of obsolete derived tables. Material
  `macro_observations` were preserved.

## Risks observed

- Some catalogued series are genuinely absent from current material facts:
  4 rates/inflation, 8 growth/labor, 1 liquidity/funding, and 8 credit rows.
  They are visible as local missing rows and do not disable a page or constrain
  DeepAgents.
- Overall `/api/status` is degraded by unrelated `resolution_refresh` and
  `news_fetch` workers. Both Macro workers are running and report no current
  error.
- The application logs contain optional LiteLLM Bedrock/SageMaker preload
  warnings because `botocore` is absent. The configured OpenAI-compatible Macro
  workflow and verified publication are unaffected.

## Follow-ups

None recorded.
