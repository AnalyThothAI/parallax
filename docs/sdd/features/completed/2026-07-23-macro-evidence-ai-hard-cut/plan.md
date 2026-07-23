# Plan — Evidence-first Macro Intel And Product-AI Hard Cut

**Status**: Verified
**Superseded by**: N/A
**Date**: 2026-07-23
**Owning spec**: `docs/sdd/features/completed/2026-07-23-macro-evidence-ai-hard-cut/spec.md`
**Worktree**: `.worktrees/macro-evidence-ai-hard-cut/`
**Branch**: `codex/macro-evidence-ai-hard-cut`
**Approved by**: delegated goal
**Approved at**: 2026-07-23

## Pre-flight

- [x] Spec is approved through delegated goal and GitHub Issue #4.
- [x] Worktree exists at `.worktrees/macro-evidence-ai-hard-cut/` and branch is `codex/macro-evidence-ai-hard-cut` at clean `main` commit `11a7fab5` before feature edits.
- [x] Baseline `uv run ruff check .` passes.
- [x] Baseline `uv run pytest -q` completed: `3662 passed, 3 failed, 2 skipped, 2 subtests passed`; exact inherited failures are listed below.

Known-failing baseline tests (none introduced by this branch):

- `tests/golden/test_token_radar_corpus.py::test_address_like_payload_symbol_does_not_mask_missing_real_symbol`
- `tests/golden/test_token_radar_corpus.py::test_gmgn_payload_identity_does_not_project_market_snapshot_into_radar`
- `tests/integration/test_docs_generated.py::test_make_docs_generated_clean_diff`

The Token Radar failures are the pre-existing explicit-transaction mismatch in
the golden helper. The generated-docs failure is pre-existing drift. Final
verification still requires every changed seam to pass and no regression over
this baseline.

## File-level edits

### Macro deep module and concept manifest

- Add `src/parallax/domains/macro_intel/services/macro_concept_manifest.py` as the one current concept ownership table: page, role, unit, frequency, freshness, legal change window, criticality, and claim effect.
- Add `src/parallax/domains/macro_intel/services/macro_evidence_snapshot.py` with external interface `build_macro_evidence_snapshot(observations: Sequence[Mapping[str, Any]], *, computed_at_ms: int) -> Mapping[str, Any]`. It returns shared metadata and exactly `overview`, `cross_asset`, `rates_inflation`, `growth_labor`, `liquidity_funding`, and `credit` documents.
- Add small internal pure-rule modules only where they reduce locality: dominant-shock state, Credit stage/direction, yield/spread quadrant, release-aware changes, return alignment/correlation, evidence/freshness construction.
- Delete `macro_regime_engine.py`, `macro_scenario_engine.py`, `macro_feature_engine.py`, `macro_module_catalog.py`, `macro_module_views.py`, all `macro_module_*.py`, `macro_assets_brief.py`, and the standalone correlation implementation after the replacement interface tests pass.
- Replace old private-module tests with table-driven tests at the evidence-snapshot interface and its pure rule seams.

### Macro projection and storage

- Change `MacroViewProjectionWorker` to load only manifest concepts, refresh compact series, invoke `build_macro_evidence_snapshot`, atomically write one stable current row, and acknowledge dirty targets.
- Replace `macro_view_snapshots` legacy columns with shared snapshot metadata plus six required JSONB page columns and `payload_hash`.
- Replace repository module lookup with six explicit page reads (or one snapshot read used by six route adapters); keep series reads independent and persisted.
- Preserve source-signature publication state, stable identity, bounded catch-up, transaction ownership, and unchanged payload-hash zero-write.

### Product-AI hard deletion

- Delete News story-brief worker, policy/admission, prompt, input/stage/validation/entity-support types, provider interface/client, run/current repositories, repair operation, worker/factory/manifest/config lane, bootstrap model construction, queue discriminator, page projection dependency, public fields, Ops/status, and tests that preserve the retired product.
- Rebuild News page projection as a fact-only projection and keep source headline/time/event/entity/dedupe/market facts.
- Delete `news_high_signal` notification behavior while retaining and positively testing watched-account notification.
- Delete SearchAgentBrief backend/frontend/tests.
- Delete Token narrative admission backend/API/frontend/tests.
- Delete semantic-catalyst and `llm_*` query/features/factor/cache/schema/API/frontend/tests; bump the surviving transparent factor/projection version.
- Retain provider-neutral structured JSON execution, capabilities, schema/usage/hash primitives, dependency, and isolated tests; remove News-specific lane IDs/knowledge and all production composition.

### Public macro contracts

- Replace generic macro Pydantic models with strict shared evidence models and six page-specific response models; use `extra="forbid"` semantics.
- Replace routes with `/macro/overview`, `/macro/cross-asset`, `/macro/rates-inflation`, `/macro/growth-labor`, `/macro/liquidity-funding`, `/macro/credit`, and `/macro/series` below the existing `/api` router prefix.
- Delete `/macro`, `/macro/modules/{module_id}`, `/macro/assets/correlation`, aliases, generic validators, and old contract tests.
- Regenerate OpenAPI and frontend generated types only after the final backend contract is green.

### Frontend product hard cut

- Replace the macro route identifier/tree/registry/universal renderer stack with six explicit route descriptors, six route components, one flat navigation, typed hooks, and a small shared evidence/page primitive set.
- Delete old asset/rates/module workbench pages, old generic models/registry/navigation, duplicate subnav/breadcrumb ownership, and feature CSS that only supports retired pages.
- Implement owner CSS under the macro feature namespace; preserve the global application shell and design tokens.
- Render Chinese decision language from backend/static vocabulary, English series/ticker/provider as secondary evidence, and all required metadata without hover-only disclosure.
- Use tables/small multiples with strict units and responsive list transformations; no dual axis, mixed-unit chart, fake tenor date, or whole-page overflow.
- Remove News and Token AI-labelled UI/fields and update fact-only views.

### Storage migration

- Preserve the already-applied worker-integrity revisions
  `20260722_0189`/`20260722_0190` byte-for-byte, then add this feature's
  Alembic revision `20260723_0191` after `20260722_0190` with bounded local
  lock/statement timeouts. The revision number changed after pre-flight found
  the operator database and active worktree had already advanced linearly.
- Drop News story-agent child/current tables and indexes, remove `story_brief` from queue constraints, and purge its dirty/terminal rows before removing runtime code.
- Drop News page AI-derived columns or replace AI-bearing JSON contracts with fact-only required columns without preserving nullable aliases.
- Drop Token semantic-catalyst cache columns and rank-source `llm_*` columns in exact dependency order.
- Replace the legacy macro snapshot columns with the six-page schema; because it is rebuildable, clear/rebuild the row rather than transform incompatible semantic JSON.
- Do not use `CASCADE` or `IF EXISTS`; `downgrade()` raises explicit irreversible backup-restore guidance.

### Canonical and generated contracts

- Update `AGENTS.md` and `CLAUDE.md` together, plus architecture, contracts, frontend, worker, worker-flow, reliability, design-discipline, model-execution, and owning domain architecture documents.
- Add project agent tracker/domain/triage routing generated by the prerequisite setup skill.
- Regenerate OpenAPI, frontend types, database schema, CLI help, and SDD work index from source.
- Scope residual guards to current supported runtime/contracts; immutable migrations and completed SDDs remain historical evidence.

### Tests

- Add one vertical macro product seam from non-empty facts through projection, seven HTTP reads, and six page contracts.
- Add one non-empty predecessor migration/runtime-composition seam covering exact AI deletion, raw-fact preservation, dormant LLM, watched-account notification, and projection zero-write.
- Add table-driven pure rules for shock state, Credit stages, quadrant, frequency windows, unit conversion, sample alignment, and critical/optional gaps.
- Add frontend route/component/responsive tests and browser verification for 1920/1366/834/390.
- Add OpenAPI/generated-type drift and negative old-route/old-field/runtime/schema guards paired with positive replacement behavior.

## PR breakdown

1. **PR 1 — Atomic evidence/product hard cut**: SDD, RED seams, product-AI deletion, migration, macro snapshot/API/frontend replacement, canonical/generated contracts, and all verification. The schema, backend, and frontend are one deployment unit and are not independently deployable.

## Analyze Gate

| Check | Result |
|-------|--------|
| Spec goals map to file-level edits. | Pass: Goals G1-G8 map to explicit macro domain, projection/storage, AI deletion, public contract, frontend, migration, docs/generated, and verification sections. |
| Plan preserves canonical architecture boundaries. | Pass: PostgreSQL facts remain truth; one writer and stable keys remain; providers/models remain outside transactions and read routes. |
| Compatibility code or old files are not retained. | Pass: every retired route, field, renderer, worker, table, alias, and pseudo-AI consumer is explicitly deleted. |
| Parallel touch/conflict sets are explicit. | Pass: Macro domain, product-AI backend, and frontend lanes are disjoint; parent owns shared API, migration, generated contracts, docs, and final integration. |

## Rollout order

1. Add failing vertical seams and exact hard-delete expectations.
2. Delete product-AI runtime and consumers while preserving positive fact paths.
3. Build the macro evidence snapshot and replace projection/storage.
4. Replace strict HTTP schemas/routes and regenerate frontend types.
5. Replace frontend routes/pages and remove AI UI.
6. Update canonical/generated contracts and run the risk-selected direct checks.
7. Before operator deployment, create a PostgreSQL backup, stop the old application, apply migration and new application together, rebuild the macro snapshot from facts, and validate seven endpoints/six pages. Operator deployment is not performed without a separate explicit instruction.

## Rollback

Before operator migration, revert the branch. After the irreversible migration, restore the pre-migration PostgreSQL backup and deploy the previous application image/config together. Do not downgrade by recreating empty tables, old fields, aliases, dual reads, or compatibility routes.

## Acceptance test commands

- AC1: `uv run pytest tests/unit/test_api_macro_contract.py tests/integration/test_api_http.py -q && cd web && npm run test -- --run tests/routes/macro.route.test.tsx`
- AC2: `uv run pytest tests/integration/domains/macro_intel/test_macro_evidence_projection.py -q`
- AC3: `uv run pytest tests/integration/domains/macro_intel/test_macro_evidence_projection.py -k zero_write -q`
- AC4: `uv run pytest tests/unit/domains/macro_intel/test_macro_evidence_snapshot.py -k judgment -q`
- AC5: `uv run pytest tests/unit/domains/macro_intel/test_macro_evidence_snapshot.py -k evidence_gap -q`
- AC6: `uv run pytest tests/unit/domains/macro_intel/test_macro_cross_asset_rules.py -q`
- AC7: `uv run pytest tests/unit/domains/macro_intel/test_macro_rates_inflation_rules.py -q`
- AC8: `uv run pytest tests/unit/domains/macro_intel/test_macro_growth_liquidity_rules.py -q`
- AC9: `uv run pytest tests/unit/domains/macro_intel/test_macro_credit_rules.py -q`
- AC10: `uv run pytest tests/unit/domains/macro_intel/test_macro_evidence_snapshot.py -k unavailable -q`
- AC11: `uv run pytest tests/architecture/test_product_ai_hard_delete.py tests/unit/test_notification_rules.py tests/unit/test_api_news_contract.py tests/unit/test_search_service.py tests/unit/test_token_case_service.py -q`
- AC12: `uv run pytest tests/architecture/test_product_ai_hard_delete.py -k dormant_llm tests/unit/integrations/model_execution -q`
- AC13: `uv run pytest tests/integration/domains/macro_intel/test_macro_evidence_projection.py tests/integration/test_macro_evidence_ai_hard_cut_migration.py tests/unit/test_macro_evidence_ai_hard_cut_migration_contract.py -q`
- AC14: `cd web && npm run lint && npm run typecheck && npm run test -- --run tests/component/features/macro tests/routes/macro.route.test.tsx`
- AC15: `uv run pytest tests/unit/domains/macro_intel/test_macro_evidence_snapshot.py -k catalysts -q`
- AC16: `uv run pytest tests/integration/test_docs_generated.py tests/contract/test_openapi_drift.py tests/architecture/test_product_ai_hard_delete.py -q && uv run python scripts/regen_sdd_work_index.py --check`

## Verification

Verification evidence lives in `docs/sdd/features/completed/2026-07-23-macro-evidence-ai-hard-cut/verification.md`.
