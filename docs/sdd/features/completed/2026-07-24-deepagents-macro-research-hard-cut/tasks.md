# Tasks — DeepAgents Macro Research Hard Cut

**Status**: Verified
**Superseded by**: N/A
**Owning plan**: `docs/sdd/features/completed/2026-07-24-deepagents-macro-research-hard-cut/plan.md`
**Worktree**: `.worktrees/deepagents-macro-hard-cut/`
**Branch**: `codex/deepagents-macro-hard-cut`
**Approved by**: user
**Approved at**: 2026-07-24

## Gate Compliance

| Gate | Evidence |
|------|----------|
| Clarify | `spec.md` records the user-approved full hard cut and semantic ownership. |
| Checklist | `spec.md` contains testable requirements and twelve acceptance criteria. |
| Analyze | `plan.md` records current owners, three interface designs, target ownership, risks, rollout, and forward recovery. |
| Implement | Tasks are ordered contract/storage/runtime/read surface/deletion/verification. |
| Verify | `verification.md` contains exact successful command receipts, real-provider publication evidence, browser inspection, and independent reviews. |

## Tasks

### Task 1 — Establish SDD and hard-cut contracts

- **File(s)**: `docs/sdd/features/completed/2026-07-24-deepagents-macro-research-hard-cut`; `tests/architecture`
- **Owner**: Codex `/root`
- **Depends on**: none
- **Touch set**: `docs/sdd/features/completed/2026-07-24-deepagents-macro-research-hard-cut`; `tests/architecture`
- **Conflict set**: `src/parallax`; `web/src`
- **Failing test first**: `tests/architecture/test_product_ai_hard_delete.py`
- **Implementation**: Encode the approved semantic boundary and add external
  behavior plus residual expectations before claiming implementation.
- **Verification**: `uv run python scripts/validate_sdd_artifacts.py`
- **Status**: [x]

### Task 2 — Add research artifact, frozen evidence scope, and tools

- **File(s)**: `src/parallax/domains/macro_intel/services`; `tests/unit/domains/macro_intel`
- **Owner**: delegated
- **Depends on**: Task 1
- **Touch set**: `src/parallax/domains/macro_intel/services`; `tests/unit/domains/macro_intel`
- **Conflict set**: `src/parallax/domains/macro_intel/repositories`; `src/parallax/domains/macro_intel/runtime`; `src/parallax/app/surfaces/api`
- **Failing test first**: `tests/unit/domains/macro_intel/test_macro_research.py`
- **Implementation**: Define the agent-owned artifact envelope and scoped
  observation/News/history query tools without deterministic semantic fields.
- **Verification**: `uv run pytest tests/unit/domains/macro_intel/test_macro_research.py -q`
- **Status**: [x]

### Task 3 — Replace derived storage with session research runs/publications

- **File(s)**: `src/parallax/platform/db/alembic/versions`; `src/parallax/domains/macro_intel/repositories`; `src/parallax/app/runtime/repository_session.py`; `tests/integration`
- **Owner**: delegated
- **Depends on**: Task 1
- **Touch set**: `src/parallax/platform/db/alembic/versions`; `src/parallax/domains/macro_intel/repositories`; `src/parallax/app/runtime/repository_session.py`; `tests/integration`
- **Conflict set**: `src/parallax/domains/macro_intel/runtime`; `docs/generated/db-schema.md`
- **Failing test first**: `tests/integration/test_deepagents_macro_research_migration.py`
- **Implementation**: Drop old projection/judgment tables and triggers; add
  bounded run lifecycle plus immutable publication storage.
- **Verification**: `uv run pytest tests/integration/test_deepagents_macro_research_migration.py tests/integration/test_macro_research_publication.py -q`
- **Status**: [x]

### Task 4 — Implement the DeepAgents Macro research runtime

- **File(s)**: `src/parallax/integrations/model_execution`; `tests/unit/integrations/model_execution`
- **Owner**: delegated
- **Depends on**: Task 2
- **Touch set**: `src/parallax/integrations/model_execution`; `tests/unit/integrations/model_execution`
- **Conflict set**: `src/parallax/app/runtime/worker_factories/macro_intel.py`; `pyproject.toml`
- **Failing test first**: `tests/unit/integrations/model_execution/test_macro_research_deepagent.py`
- **Implementation**: Build the single deep runtime with scoped tools,
  declarative specialists, no forced tool-order middleware, and mechanical
  citation/session validation.
- **Verification**: `uv run pytest tests/unit/integrations/model_execution/test_macro_research_deepagent.py -q`
- **Status**: [x]

### Task 5 — Replace two derived workers with one research worker

- **File(s)**: `src/parallax/domains/macro_intel/runtime`; `src/parallax/platform/config/settings.py`; `src/parallax/app/runtime/worker_manifest.py`; `src/parallax/app/runtime/worker_factories/macro_intel.py`; `tests/unit`
- **Owner**: delegated
- **Depends on**: Task 3, Task 4
- **Touch set**: `src/parallax/domains/macro_intel/runtime`; `src/parallax/platform/config/settings.py`; `src/parallax/app/runtime/worker_manifest.py`; `src/parallax/app/runtime/worker_factories/macro_intel.py`; `tests/unit`
- **Conflict set**: `src/parallax/app/surfaces/api`; `docs/sdd`
- **Failing test first**: `tests/unit/domains/macro_intel/test_macro_research_worker.py`
- **Implementation**: Schedule one completed session, claim/retry through
  PostgreSQL, call the deep runtime outside write transactions, and publish
  atomically.
- **Verification**: `uv run pytest tests/unit/domains/macro_intel/test_macro_research_worker.py tests/unit/test_worker_factories.py tests/unit/test_worker_settings.py -q`
- **Status**: [x]

### Task 6 — Replace public reads with one persisted research API

- **File(s)**: `src/parallax/app/surfaces/api`; `docs/generated`; `web/src/lib/types`; `tests/unit/test_api_macro_contract.py`
- **Owner**: delegated
- **Depends on**: Task 3
- **Touch set**: `src/parallax/app/surfaces/api`; `docs/generated`; `web/src/lib/types`; `tests/unit/test_api_macro_contract.py`
- **Conflict set**: `web/src/features/macro`
- **Failing test first**: `tests/unit/test_api_macro_contract.py`
- **Implementation**: Add `/api/macro/research`, delete page/series/Daily routes
  and schemas, and prove zero model/provider calls on reads.
- **Verification**: `make regen-contract && uv run pytest tests/unit/test_api_macro_contract.py tests/contract/test_openapi_drift.py -q`
- **Status**: [x]

### Task 7 — Rebuild `/macro` as one Chinese research workbench

- **File(s)**: `web/src/features/macro`; `web/src/routes/router.tsx`; `web/tests`
- **Owner**: delegated
- **Depends on**: Task 6
- **Touch set**: `web/src/features/macro`; `web/src/routes/router.tsx`; `web/tests`
- **Conflict set**: `web/src/lib/types`
- **Failing test first**: `tests/routes/macro.route.test.tsx::renders_macro_research`
- **Implementation**: Replace six pages and Daily card with one responsive
  persisted research document and remove all child routes.
- **Verification**: `cd web && npm test -- --run tests/routes/macro.route.test.tsx tests/architecture/macroResearchHardCut.test.ts`
- **Status**: [x]

### Task 8 — Hard-delete deterministic judgment and dormant LLM modules

- **File(s)**: `src/parallax/domains/macro_intel`; `src/parallax/integrations/model_execution`; `src/parallax/platform`; `tests/architecture`; `pyproject.toml`; `uv.lock`
- **Owner**: Codex `/root`
- **Depends on**: Task 2, Task 3, Task 4, Task 5, Task 6, Task 7
- **Touch set**: `src/parallax/domains/macro_intel`; `src/parallax/integrations/model_execution`; `src/parallax/platform`; `tests/architecture`; `pyproject.toml`; `uv.lock`
- **Conflict set**: `src/parallax/domains/macro_intel/services`; `src/parallax/integrations/model_execution`; `src/parallax/app/runtime`; `src/parallax/app/surfaces/api`; `web/src/features/macro`
- **Failing test first**: `tests/architecture/test_product_ai_hard_delete.py`
- **Implementation**: Remove old rule/snapshot/evidence-pack/Daily sources,
  tests, config names, aliases, wrappers, and direct LiteLLM dependency.
- **Verification**: `uv run pytest tests/architecture/test_product_ai_hard_delete.py tests/architecture/test_kiss_runtime_invariants.py -q`
- **Status**: [x]

### Task 9 — Align canonical docs and generated artifacts

- **File(s)**: `docs/`; `config.example.yaml`; `web/src/lib/types`
- **Owner**: Codex `/root`
- **Depends on**: Task 5, Task 6, Task 7, Task 8
- **Touch set**: `docs/`; `config.example.yaml`; `web/src/lib/types`
- **Conflict set**: `src/parallax/app/surfaces/api`; `src/parallax/platform/db/alembic/versions`
- **Failing test first**: `tests/unit/test_docs_contract.py`
- **Implementation**: Document the one fact plane, one agent research runtime,
  one publication/read surface, operational lifecycle, and removed contracts.
- **Verification**: `make docs-generated && make regen-contract && uv run pytest tests/unit/test_docs_contract.py tests/contract/test_openapi_drift.py -q`
- **Status**: [x]

### Task 10 — Verify runtime, semantic quality, and complete the hard cut

- **File(s)**: `docs/sdd/features/completed/2026-07-24-deepagents-macro-research-hard-cut`; `docs/generated/sdd-work-index.md`
- **Owner**: Codex `/root`
- **Depends on**: Task 1, Task 2, Task 3, Task 4, Task 5, Task 6, Task 7, Task 8, Task 9
- **Touch set**: `docs/sdd/features/completed/2026-07-24-deepagents-macro-research-hard-cut`; `docs/generated/sdd-work-index.md`
- **Conflict set**: `src/parallax`; `tests/unit`; `web/src`; `docs/sdd`
- **Failing test first**: `tests/unit/test_validate_sdd_artifacts.py`
- **Implementation**: Run focused/full selected tests, non-empty migration,
  real provider publication, blind semantic review, browser inspection,
  residual scans, and record exact receipts before moving SDD to completed.
- **Verification**: `uv run python scripts/check_sdd_gate.py --feature 2026-07-24-deepagents-macro-research-hard-cut --gate verify`
- **Status**: [x]
