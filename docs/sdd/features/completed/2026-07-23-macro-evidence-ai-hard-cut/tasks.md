# Tasks — Evidence-first Macro Intel And Product-AI Hard Cut

**Status**: Verified
**Superseded by**: N/A
**Owning plan**: `docs/sdd/features/completed/2026-07-23-macro-evidence-ai-hard-cut/plan.md`
**Worktree**: `.worktrees/macro-evidence-ai-hard-cut/`
**Branch**: `codex/macro-evidence-ai-hard-cut`
**Approved by**: delegated goal
**Approved at**: 2026-07-23

## Gate Compliance

| Gate | Evidence |
|------|----------|
| Clarify | `spec.md` records the approved page, judgment, data, AI deletion, migration, UI, language, freshness, deployment, and no-compat decisions. |
| Checklist | `spec.md` maps each product/runtime/storage/UI requirement to an executable quality gate. |
| Analyze | `plan.md` maps G1-G8 and AC1-AC16 to disjoint edits and commands, preserving Kappa/CQRS and hard-cut rules. |
| Implement | Tasks are ordered RED seams, disjoint domain work, shared integration, contracts/UI, docs/generated, then final verification. |
| Verify | `verification.md` records successful direct commands for every acceptance criterion. |

## Tasks

### Task 1 — Establish RED vertical and hard-delete seams

- **File(s)**: `tests/architecture/test_product_ai_hard_delete.py`, `tests/integration/domains/macro_intel/test_macro_evidence_projection.py`, `tests/unit/test_api_macro_contract.py`, `web/tests/routes/**`
- **Owner**: parent
- **Depends on**: none
- **Touch set**: `tests/architecture/test_product_ai_hard_delete.py`, `tests/integration/domains/macro_intel/test_macro_evidence_projection.py`, `tests/unit/test_api_macro_contract.py`, `web/tests/routes/**`, `docs/sdd/features/completed/2026-07-23-macro-evidence-ai-hard-cut/**`
- **Conflict set**: `src/parallax/**`, `web/src/**`; coordinate with 2026-07-22-backend-kiss-deep-audit for all overlapping runtime/domain/API/test/docs paths; coordinate with 2026-07-22-news-fetch-retention-index for tests/unit/test_postgres_schema.py and tests/integration/test_postgres_schema_runtime.py
- **Failing test first**: `tests/architecture/test_product_ai_hard_delete.py::test_current_product_ai_runtime_and_contracts_are_absent` rejects current AI runtime/schema/API/frontend ownership; vertical macro contract rejects legacy modules.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Implementation**: Add behavior-first replacement expectations and narrowly scoped hard-delete guards before modifying production code.
- **Verification**: `uv run pytest tests/architecture/test_product_ai_hard_delete.py tests/unit/test_api_macro_contract.py -q`
- **Review owner**: parent
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Pair negative retirement assertions with positive raw-fact/page behavior; do not scan immutable history or freeze private source wording.
- **On-demand context**: Spec AC1-AC16, current routes/worker manifest/schema/frontend registry, Testing and read-model checklist.
- **Kill/defer criteria**: Reject a guard that can pass while a real consumer remains or fail only because historical evidence names a retired surface.
- **Eval/repair signal**: Initial RED node IDs, later green behavior, and review defect count.
- **Status**: [x]

### Task 2 — Delete product-AI runtime and preserve fact paths `[P]`

- **File(s)**: `src/parallax/domains/news_intel/**`, `src/parallax/domains/token_intel/**`, `src/parallax/domains/notifications/**`, `src/parallax/app/runtime/**`, `src/parallax/app/operations/news.py`, `src/parallax/platform/agent_*.py`, `src/parallax/integrations/model_execution/**`, `tests/unit/domains/news_intel/**`, `tests/unit/domains/token_intel/**`, `tests/unit/domains/notifications/**`, `tests/unit/integrations/model_execution/**`
- **Owner**: `/root/ai_hardcut_impl` (write-allowed bounded delegation)
- **Depends on**: none
- **Touch set**: `src/parallax/domains/news_intel/**`, `src/parallax/domains/token_intel/**`, `src/parallax/domains/notifications/**`, `src/parallax/app/runtime/**`, `src/parallax/app/operations/news.py`, `src/parallax/platform/agent_*.py`, `src/parallax/integrations/model_execution/**`, `tests/unit/domains/news_intel/**`, `tests/unit/domains/token_intel/**`, `tests/unit/domains/notifications/**`, `tests/unit/integrations/model_execution/**`
- **Conflict set**: `src/parallax/app/surfaces/api/**`, `src/parallax/platform/db/alembic/versions/**`, `src/parallax/domains/macro_intel/**`, `web/**`, `docs/generated/**`
- **Failing test first**: `tests/unit/domains/news_intel/test_news_page_projection.py::test_news_page_projection_serves_source_facts_without_agent_brief` asserts the replacement fact path before deletion.
- **Subagent handoff**: `docs/generated/subagent-handoffs/macro-evidence-ai-hard-cut-task-2.md`
- **Subagent report**: `docs/generated/subagent-reports/macro-evidence-ai-hard-cut-task-2.md`
- **Review result**: accepted
- **Implementation**: Delete real/pseudo AI producers, workers, policies, consumers, and factor wiring within owned backend scope; retain raw facts, watched-account behavior, and dormant provider-neutral primitives.
- **Verification**: `uv run pytest tests/unit/domains/news_intel tests/unit/domains/token_intel tests/unit/domains/notifications tests/unit/integrations/model_execution -q`
- **Review owner**: parent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: no disabled lane, alias, renamed pseudo AI, template replacement, provider I/O in DB transaction, or raw-fact deletion.
- **On-demand context**: News/Token/notification architecture maps, AGENT_EXECUTION, WORKERS, WORKER_FLOW, current worker manifest and bootstrap.
- **Kill/defer criteria**: stop and report any verified non-AI consumer of a deletion target; do not invent compatibility.
- **Eval/repair signal**: domain test failures, residual owned-scope imports, surviving fact-path assertions.
- **Status**: [x]

### Task 3 — Build the macro evidence snapshot deep module `[P]`

- **File(s)**: `src/parallax/domains/macro_intel/services/**`, `src/parallax/domains/macro_intel/_constants.py`, `tests/unit/domains/macro_intel/**`
- **Owner**: `/root/macro_backend_impl` (write-allowed bounded delegation)
- **Depends on**: none
- **Touch set**: `src/parallax/domains/macro_intel/services/**`, `src/parallax/domains/macro_intel/_constants.py`, `tests/unit/domains/macro_intel/**`
- **Conflict set**: `src/parallax/domains/macro_intel/runtime/**`, `src/parallax/domains/macro_intel/repositories/**`, `src/parallax/app/**`, `src/parallax/platform/db/**`, `web/**`, `docs/generated/**`
- **Failing test first**: `tests/unit/domains/macro_intel/test_macro_evidence_snapshot.py::test_builds_exact_six_page_documents` asserts exact six documents, judgment/freshness metadata, domain skeletons, and fail-closed behavior.
- **Subagent handoff**: `docs/generated/subagent-handoffs/macro-evidence-ai-hard-cut-task-3.md`
- **Subagent report**: `docs/generated/subagent-reports/macro-evidence-ai-hard-cut-task-3.md`
- **Review result**: accepted
- **Implementation**: Create the concept manifest and deep evidence-snapshot interface; implement pure domain rules and delete the generic score/module implementation.
- **Verification**: `uv run pytest tests/unit/domains/macro_intel -q`
- **Review owner**: parent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: existing facts only; latest-vintage; frequency-aware windows; no global score, percentages, trade text, proxy evidence, or generic module interface.
- **On-demand context**: macro ARCHITECTURE, existing services end to end, current observation shapes, approved Spec domain skeletons.
- **Kill/defer criteria**: report missing concept evidence as unavailable; do not add a provider, placeholder, universal fallback, or configuration-driven rule.
- **Eval/repair signal**: rule matrix failures, uncovered metadata, interface size/locality review.
- **Status**: [x]

### Task 4 — Replace macro projection/storage and add irreversible migration

- **File(s)**: `src/parallax/domains/macro_intel/runtime/macro_view_projection_worker.py`, `src/parallax/domains/macro_intel/repositories/macro_intel_repository.py`, `src/parallax/platform/db/alembic/versions/**`, `tests/integration/domains/macro_intel/test_macro_evidence_projection.py`, `tests/integration/test_postgres_schema_runtime.py`, `tests/unit/test_postgres_schema.py`
- **Owner**: parent
- **Depends on**: Tasks 2-3
- **Touch set**: `src/parallax/domains/macro_intel/runtime/macro_view_projection_worker.py`, `src/parallax/domains/macro_intel/repositories/macro_intel_repository.py`, `src/parallax/platform/db/alembic/versions/**`, `tests/integration/domains/macro_intel/test_macro_evidence_projection.py`, `tests/integration/test_postgres_schema_runtime.py`, `tests/unit/test_postgres_schema.py`
- **Conflict set**: `src/parallax/domains/macro_intel/services/**`, `src/parallax/app/surfaces/api/**`, `web/**`
- **Failing test first**: `tests/integration/domains/macro_intel/test_macro_evidence_projection.py::test_non_empty_projection_replay_is_atomic_and_zero_write` fails until exact drops, six-page storage, fact retention, atomic ack, and second-run zero-write exist.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Implementation**: Integrate the deep builder into one writer, replace legacy storage/read methods, and perform exact irreversible AI/macro schema hard cut.
- **Verification**: `uv run pytest tests/integration/domains/macro_intel/test_macro_evidence_projection.py tests/integration/test_macro_evidence_ai_hard_cut_migration.py tests/unit/test_macro_evidence_ai_hard_cut_migration_contract.py -q`
- **Review owner**: parent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: stable key, payload hash, one writer, bounded timeouts, child-first exact drops, no CASCADE/IF EXISTS, raw facts preserved.
- **On-demand context**: read-model checklist, Alembic head/schema, News/Token storage inventory, repository SQL.
- **Kill/defer criteria**: stop if exact dependency inventory is incomplete; never use broad DDL to force success.
- **Eval/repair signal**: migration upgrade errors, row-count preservation, write-amplification count, integration defects.
- **Status**: [x]

### Task 5 — Replace strict HTTP contracts and runtime composition

- **File(s)**: `src/parallax/app/surfaces/api/routes_macro.py`, `src/parallax/app/surfaces/api/routes_news.py`, `src/parallax/app/surfaces/api/schemas.py`, `src/parallax/app/surfaces/api/validators.py`, `src/parallax/app/runtime/bootstrap.py`, `src/parallax/app/runtime/worker_factories/news_intel.py`, `src/parallax/app/runtime/worker_manifest.py`, `src/parallax/platform/config/settings.py`, `src/parallax/app/surfaces/cli/**`, `tests/unit/test_api_macro_contract.py`, `tests/unit/test_api_news_contract.py`, `tests/contract/test_openapi_drift.py`
- **Owner**: parent
- **Depends on**: Tasks 2-4
- **Touch set**: `src/parallax/app/surfaces/api/routes_macro.py`, `src/parallax/app/surfaces/api/routes_news.py`, `src/parallax/app/surfaces/api/schemas.py`, `src/parallax/app/surfaces/api/validators.py`, `src/parallax/app/runtime/bootstrap.py`, `src/parallax/app/runtime/worker_factories/news_intel.py`, `src/parallax/app/runtime/worker_manifest.py`, `src/parallax/platform/config/settings.py`, `src/parallax/app/surfaces/cli/**`, `tests/unit/test_api_macro_contract.py`, `tests/unit/test_api_news_contract.py`, `tests/contract/test_openapi_drift.py`
- **Conflict set**: `src/parallax/domains/macro_intel/services/**`, `src/parallax/platform/db/alembic/versions/**`, `web/**`
- **Failing test first**: `tests/unit/test_api_macro_contract.py::test_macro_pages_have_exact_typed_contracts` rejects legacy snapshot/module fields and AI News/Token fields.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Implementation**: Publish seven strict macro reads, fact-only News/Token/Search contracts, remove old routes/runtime/config/status/repair paths, and leave LLM primitives dormant.
- **Verification**: `uv run pytest tests/unit/test_api_macro_contract.py tests/unit/test_api_news_contract.py tests/integration/test_api_http.py tests/contract/test_openapi_drift.py tests/unit/test_settings.py tests/unit/test_worker_factories.py -q`
- **Review owner**: parent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: API reads persisted projections only; `extra=forbid`; old paths ordinary 404; no nullable compatibility field or bootstrap model instance.
- **On-demand context**: CONTRACTS, API router dependencies, runtime snapshot, worker settings and factories.
- **Kill/defer criteria**: do not publish until all six pages share one stored snapshot version/watermark.
- **Eval/repair signal**: schema validation errors, OpenAPI drift, runtime composition defects.
- **Status**: [x]

### Task 6 — Hard-cut frontend to six explicit pages and fact-only AI consumers

- **File(s)**: `web/**`
- **Owner**: `/root/frontend_hardcut_impl` (write-allowed bounded delegation)
- **Depends on**: Task 5
- **Touch set**: `web/`
- **Conflict set**: `src/`, `docs/`; coordinate with 2026-07-22-docker-build-contract-fix for `web/src/lib/api/client.ts`, `web/src/lib/types/index.ts`, `web/tests/component/features/news/NewsPage.test.tsx`, `web/tests/component/features/news/NewsTape.test.tsx`, `web/tests/unit/features/notifications/api/notifications.test.ts`, and `web/tests/unit/features/notifications/useNotificationsController.test.tsx`
- **Failing test first**: `tests/routes/macro.route.test.tsx::renders six explicit macro routes` requires six pages, flat nav, old-route 404, typed evidence rendering, fact-only News/Token/Search, and responsive transformations.
- **Subagent handoff**: `docs/generated/subagent-handoffs/macro-evidence-ai-hard-cut-task-6.md`
- **Subagent report**: `docs/generated/subagent-reports/macro-evidence-ai-hard-cut-task-6.md`
- **Review result**: accepted
- **Implementation**: Replace macro UI with explicit pages/hooks/primitives and owner CSS; delete generic/AI consumers; preserve global shell and accessible responsive behavior.
- **Verification**: `cd web && npm run lint && npm run typecheck && npm run test -- --run tests/component/features/macro tests/routes/macro.route.test.tsx`
- **Review owner**: parent
- **Factory lane**: Domain implementation
- **Deterministic constraints**: no frontend scoring/fallback translation, no hidden metadata, no new UI library, owner CSS only, no whole-page overflow.
- **On-demand context**: FRONTEND, generated types, current route shell, existing component tests and CSS harness.
- **Kill/defer criteria**: stop if backend generated types are stale; never handwrite a parallel compatibility contract.
- **Eval/repair signal**: lint architecture errors, type drift, route/component/browser defects.
- **Status**: [x]

### Task 7 — Align canonical docs and generated contracts

- **File(s)**: `AGENTS.md`, `CLAUDE.md`, `docs/ARCHITECTURE.md`, `docs/CONTRACTS.md`, `docs/FRONTEND.md`, `docs/RELIABILITY.md`, `docs/WORKERS.md`, `docs/WORKER_FLOW.md`, `docs/AGENT_EXECUTION.md`, `docs/DESIGN_DISCIPLINE.md`, `src/parallax/domains/*/ARCHITECTURE.md`, `docs/generated/**`
- **Owner**: parent
- **Depends on**: Tasks 4-6
- **Touch set**: `AGENTS.md`, `CLAUDE.md`, `docs/ARCHITECTURE.md`, `docs/CONTRACTS.md`, `docs/FRONTEND.md`, `docs/RELIABILITY.md`, `docs/WORKERS.md`, `docs/WORKER_FLOW.md`, `docs/AGENT_EXECUTION.md`, `docs/DESIGN_DISCIPLINE.md`, `src/parallax/domains/*/ARCHITECTURE.md`, `docs/generated/**`
- **Conflict set**: `src/parallax/**/*.py`, `web/**`; coordinate with 2026-07-23-verification-harness-hard-cut for AGENTS.md, CLAUDE.md, docs/DESIGN_DISCIPLINE.md, and docs/generated/sdd-work-index.md
- **Failing test first**: `tests/integration/test_docs_generated.py::test_generated_docs_match_runtime` fails until current product truth no longer claims old module/AI surfaces.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Implementation**: Rewrite current architecture/contracts to the new truth, mirror routers, preserve historical evidence, and regenerate all source-derived artifacts.
- **Verification**: `uv run pytest tests/integration/test_docs_generated.py tests/contract/test_openapi_drift.py tests/architecture/test_product_ai_hard_delete.py -q && uv run python scripts/regen_sdd_work_index.py --check`
- **Review owner**: parent
- **Factory lane**: Docs/contracts
- **Deterministic constraints**: generated outputs come from generators; no hand-edited drift; router shared block stays identical.
- **On-demand context**: canonical docs, generators, final diff, worker/schema/OpenAPI inventories.
- **Kill/defer criteria**: do not delete immutable historical migrations or completed SDDs to satisfy a current-contract scan.
- **Eval/repair signal**: docs/regen/SDD harness failures and residual current-contract references.
- **Status**: [x]

### Task 8 — Complete real runtime, browser, selected verification, and independent review

- **File(s)**: `docs/sdd/features/completed/2026-07-23-macro-evidence-ai-hard-cut/verification.md`
- **Owner**: parent with review-only subagent
- **Depends on**: Tasks 1-7
- **Touch set**: `docs/sdd/features/completed/2026-07-23-macro-evidence-ai-hard-cut/verification.md`
- **Conflict set**: `src/**`, `web/**`, `tests/**`
- **Failing test first**: `tests/architecture/test_product_ai_hard_delete.py::test_current_product_ai_runtime_and_contracts_are_absent` remains RED until every AC row has authoritative evidence and the verify gate passes.
- **Subagent handoff**: `docs/generated/subagent-handoffs/macro-evidence-ai-hard-cut-task-8.md`
- **Subagent report**: `docs/generated/subagent-reports/macro-evidence-ai-hard-cut-task-8.md`
- **Review result**: accepted
- **Implementation**: Repair discovered defects, verify operator-path config without secrets, non-empty migration, Docker health/readiness/queues, seven APIs, four viewports, key value metadata, risk-selected commands, and SDD completion.
- **Verification**: `uv run pytest tests/architecture/test_product_ai_hard_delete.py tests/unit/test_macro_evidence_ai_hard_cut_migration_contract.py -q`
- **Review owner**: independent validator then parent
- **Factory lane**: Final integration
- **Deterministic constraints**: no compatibility mocks, no completion from static scan alone, no secret output, no live destructive migration without backup and explicit deployment instruction.
- **On-demand context**: final spec/plan/tasks/diff, real redacted config diagnostics, Docker/browser receipts, and direct command transcripts.
- **Kill/defer criteria**: keep feature active until every requirement has direct evidence; do not downgrade the claim.
- **Eval/repair signal**: independent defects, selected-command failures, repair-loop count, false-completion count.
- **Status**: [x]
