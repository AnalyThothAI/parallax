# Tasks — Daily Macro SPY Judgment

**Status**: Verified
**Owning plan**: `docs/sdd/features/completed/2026-07-23-daily-macro-spy-judgment/plan.md`
**Worktree**: `.worktrees/daily-macro-spy-judgment/`
**Branch**: `codex/daily-macro-spy-judgment`
**Approved by**: delegated user goal and GitHub Issue #6
**Approved at**: 2026-07-23

## Gate Compliance

| Gate | Evidence |
|------|----------|
| Clarify | Issue #6 and `spec.md` fix SPY-only scope, four directions, immutable lifecycle, two-role topology, failure semantics, and out-of-scope items. |
| Checklist | `spec.md` maps every product, evidence, runtime, read, migration, and real-provider requirement to a quality gate. |
| Analyze | `plan.md` records current database, model-runtime, transaction, API, and architecture seams before implementation. |
| Implement | Tasks 1-8 require failing tests first and cover storage through runtime/API/docs without a generic AI platform. |
| Verify | Task 9 owns focused PostgreSQL, generated contract, full checks, Docker runtime, shadow receipt, and requirement-by-requirement closure. |

## Tasks

### Task 1 — Lock strict domain, calendar, eligibility, and renderer contracts

- **File(s)**: `src/parallax/domains/macro_intel/`; `tests/unit/domains/macro_intel/`
- **Owner**: Codex `/root`
- **Depends on**: None
- **Touch set**: `src/parallax/domains/macro_intel/`; `tests/unit/domains/macro_intel/`
- **Conflict set**: `src/parallax/integrations/model_execution/`; `src/parallax/platform/db/`
- **Failing test first**: `tests/unit/domains/macro_intel/test_daily_macro_judgment.py::test_contract_rejects_scores_probabilities_and_non_spy_calls`
- **Implementation**: Add strict EvidencePack/Judgment/Reviewer/outcome models, completed-session calendar helpers, conservative availability selection, health policy, deterministic gates, and fixed Chinese rendering.
- **Verification**: `uv run pytest tests/unit/domains/macro_intel/test_daily_macro_judgment.py tests/unit/domains/macro_intel/test_macro_evidence_pack.py -q`
- **Status**: [x]

### Task 2 — Add immutable PostgreSQL lifecycle and non-empty migration proof

- **File(s)**: `src/parallax/platform/db/`; `src/parallax/domains/macro_intel/repositories/`; `tests/integration/`
- **Owner**: Codex `/root`
- **Depends on**: Task 1
- **Touch set**: `src/parallax/platform/db/`; `src/parallax/domains/macro_intel/repositories/`; `tests/integration/`
- **Conflict set**: `src/parallax/domains/macro_intel/runtime/`; `src/parallax/app/`
- **Failing test first**: `tests/integration/test_daily_macro_judgment_migration.py::test_migration_preserves_existing_macro_and_news_truth_and_creates_immutable_history`
- **Implementation**: Add session-keyed jobs, immutable publications, append-only outcomes, constraints/triggers/indexes, and repository transaction methods without reviving retired brief tables.
- **Verification**: `uv run pytest tests/integration/test_daily_macro_judgment_migration.py -q`
- **Status**: [x]

### Task 3 — Prove the full PostgreSQL publication seam

- **File(s)**: `src/parallax/domains/macro_intel/`; `src/parallax/platform/db/`; `tests/integration/domains/macro_intel/`
- **Owner**: Codex `/root`
- **Depends on**: Task 1, Task 2
- **Touch set**: `src/parallax/domains/macro_intel/`; `src/parallax/platform/db/`; `tests/integration/domains/macro_intel/`
- **Conflict set**: `src/parallax/integrations/model_execution/`; `src/parallax/app/surfaces/api/`
- **Failing test first**: `tests/integration/domains/macro_intel/test_daily_macro_judgment_publication.py::test_point_in_time_facts_publish_one_immutable_judgment_and_append_outcomes`
- **Implementation**: Exercise real assembler, repository, transaction, fake Agent adapter, reviewer branches, gates, renderer, idempotency, retry state, and 5D/20D outcome attachment against non-empty PostgreSQL.
- **Verification**: `uv run pytest tests/integration/domains/macro_intel/test_daily_macro_judgment_publication.py -q`
- **Status**: [x]

### Task 4 — Integrate real DeepAgents Analyst and isolated Reviewer

- **File(s)**: `src/parallax/integrations/model_execution/`; `tests/unit/integrations/model_execution/`; `pyproject.toml`
- **Owner**: Codex `/root`
- **Depends on**: Task 1
- **Touch set**: `src/parallax/integrations/model_execution/`; `tests/unit/integrations/model_execution/`; `pyproject.toml`
- **Conflict set**: `src/parallax/domains/macro_intel/runtime/`; `src/parallax/platform/db/`
- **Failing test first**: `tests/unit/integrations/model_execution/test_macro_judgment_deepagent.py::test_analyst_uses_create_deep_agent_and_native_task_for_isolated_review`
- **Implementation**: Pin DeepAgents and LangChain LiteLLM adapter, register a least-capability harness, expose only pack-read/draft-submit tools, wire explicit Analyst and Reviewer model identities through one provider boundary, invoke the declarative Reviewer through `task`, enforce one revision, and return sanitized structured audit.
- **Verification**: `uv run pytest tests/unit/integrations/model_execution/test_macro_judgment_deepagent.py -q`
- **Status**: [x]

### Task 5 — Wire one bounded daily worker and outcome maturation

- **File(s)**: `src/parallax/domains/macro_intel/runtime/`; `src/parallax/app/runtime/`; `src/parallax/platform/config/`; `tests/unit/domains/macro_intel/`
- **Owner**: Codex `/root`
- **Depends on**: Task 2, Task 3, Task 4
- **Touch set**: `src/parallax/domains/macro_intel/runtime/`; `src/parallax/app/runtime/`; `src/parallax/platform/config/`; `tests/unit/domains/macro_intel/`
- **Conflict set**: `src/parallax/app/surfaces/api/`; `docs/`
- **Failing test first**: `tests/unit/domains/macro_intel/test_daily_macro_judgment_worker.py::test_worker_model_io_is_transaction_free_and_failure_state_is_deterministic`
- **Implementation**: Add worker settings/manifest/factory, session settle and bounded catch-up, frozen-pack retry, safe errors, single-writer ownership, transaction-free model I/O, atomic finalization, and append-only matured outcomes.
- **Verification**: `uv run pytest tests/unit/domains/macro_intel/test_daily_macro_judgment_worker.py tests/architecture/test_kiss_runtime_invariants.py -q`
- **Status**: [x]

### Task 6 — Add the persisted-only typed read contract

- **File(s)**: `src/parallax/app/surfaces/api/`; `tests/unit/`; `tests/contract/`; `web/src/`
- **Owner**: Codex `/root`
- **Depends on**: Task 2, Task 3
- **Touch set**: `src/parallax/app/surfaces/api/`; `tests/unit/`; `tests/contract/`; `web/src/`
- **Conflict set**: `src/parallax/domains/macro_intel/runtime/`; `web/src/features/macro/`
- **Failing test first**: `tests/unit/test_api_macro_contract.py::test_daily_macro_judgment_reads_typed_persisted_job_state_without_model_calls`
- **Implementation**: Add one latest/explicit-session endpoint with current/stale/job/missing semantics and outcomes, regenerate OpenAPI and TypeScript, and make no frontend route or design change.
- **Verification**: `uv run pytest tests/unit/test_api_macro_contract.py tests/contract/test_openapi_drift.py -q`
- **Status**: [x]

### Task 7 — Narrow architecture guards to the single authorized model lane

- **File(s)**: `tests/architecture/`; `src/parallax/integrations/model_execution/`; `src/parallax/domains/macro_intel/`
- **Owner**: Codex `/root`
- **Depends on**: Task 4, Task 5
- **Touch set**: `tests/architecture/`; `src/parallax/integrations/model_execution/`; `src/parallax/domains/macro_intel/`
- **Conflict set**: `src/parallax/app/surfaces/api/`; `docs/`
- **Failing test first**: `tests/architecture/test_product_ai_hard_delete.py::test_only_daily_macro_worker_factory_may_import_product_model_runtime`
- **Implementation**: Preserve broad no-Product-AI guards, allow only the named integration/factory seam, and explicitly reject LLM use in six-page Macro, News, Token, and other app/domain paths plus prohibited Agent capabilities.
- **Verification**: `uv run pytest tests/architecture/test_product_ai_hard_delete.py tests/architecture/test_kiss_runtime_invariants.py -q`
- **Status**: [x]

### Task 8 — Align canonical architecture, contracts, operations, and dependency records

- **File(s)**: `docs/`; `src/parallax/domains/macro_intel/ARCHITECTURE.md`; `pyproject.toml`; `uv.lock`
- **Owner**: Codex `/root`
- **Depends on**: Task 5, Task 6, Task 7
- **Touch set**: `docs/`; `src/parallax/domains/macro_intel/ARCHITECTURE.md`; `pyproject.toml`; `uv.lock`
- **Conflict set**: `src/parallax/app/`; `tests/`
- **Failing test first**: `tests/unit/test_docs_contract.py::test_daily_macro_judgment_docs_match_runtime_contract`
- **Implementation**: Document the independent immutable lane, point-in-time policy, worker and failure semantics, API, security boundary, operational commands, pinned versions, experimental label, and unchanged six-document current identity.
- **Verification**: `uv run pytest tests/unit/test_docs_contract.py tests/contract/test_openapi_drift.py -q`
- **Status**: [x]

### Task 9 — Verify the actual runtime and close every requirement

- **File(s)**: `docs/sdd/features/active/2026-07-23-daily-macro-spy-judgment/`; `Dockerfile`; `compose.yaml`; `Makefile`
- **Owner**: Codex `/root`
- **Depends on**: Task 1, Task 2, Task 3, Task 4, Task 5, Task 6, Task 7, Task 8
- **Touch set**: `docs/sdd/features/active/2026-07-23-daily-macro-spy-judgment/`; `Dockerfile`; `compose.yaml`; `Makefile`
- **Conflict set**: `src/`; `tests/`; `web/`
- **Failing test first**: `tests/unit/test_validate_sdd_artifacts.py::test_verified_feature_rejects_cited_command_without_successful_evidence`
- **Implementation**: Run focused and full suites, non-empty migration, image/readiness, real worker/API inspection, redacted real-provider Analyst→Reviewer shadow smoke, residual scans, requirement audit, evidence recording, and move the feature to completed only after verify gate passes.
- **Verification**: `uv run pytest tests/unit/test_validate_sdd_artifacts.py -q`
- **Status**: [x]

### Task 10 — Expose the persisted judgment on Macro Overview

- **File(s)**: `web/src/features/macro/`; `web/tests/`; `docs/FRONTEND.md`; `docs/sdd/features/completed/2026-07-23-daily-macro-spy-judgment/`
- **Owner**: Codex `/root`
- **Depends on**: Task 6, Task 9
- **Touch set**: `web/src/features/macro/`; `web/tests/`; `docs/`
- **Conflict set**: `web/src/features/macro/ui/pages/MacroOverviewPage.tsx`
- **Implementation**: Add one compact persisted Daily AI section to `/macro`, preserve the deterministic eight-lane map, expose explicit generation/error states, and make no request-time model call or new route.
- **Verification**: Frontend route, architecture, type, lint, build, responsive Playwright, rebuilt-image, and production-browser checks.
- **Status**: [ ]
