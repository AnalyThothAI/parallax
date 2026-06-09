# Tasks — Executable Harness Hard Cut

**Status**: In Progress
**Owning plan**: `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut/plan.md`
**Worktree**: `.worktrees/agent-factory-eval-harness`
**Branch**: `codex/agent-factory-eval-harness`
**Approved by**: qinghuan
**Approved at**: 2026-06-09

## Gate Compliance

| Gate | Evidence |
|------|----------|
| Clarify | `spec.md` includes `## Clarifications`. |
| Checklist | `spec.md` includes `## Requirement Checklist`. |
| Analyze | `plan.md` includes `## Analyze Gate`. |
| Implement | Tasks below are TDD ordered. |
| Verify | `verification.md` will capture command output. |

## Tasks

### Task 1 — SDD validator

- **File(s)**: `tests/architecture/test_sdd_artifact_validator.py`, `scripts/validate_sdd_artifacts.py`
- **Owner**: parent
- **Depends on**: none
- **Touch set**: `tests/architecture/test_sdd_artifact_validator.py`, `scripts/validate_sdd_artifacts.py`
- **Conflict set**: `scripts/regen_sdd_work_index.py`
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_successful_make_check_all_evidence` — asserts false `Verified` records fail.
- **Subagent handoff**: not delegated
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `uv run python scripts/validate_sdd_artifacts.py --check`, deterministic issue codes, no `Verified` status without full `make check-all` evidence.
- **On-demand context**: `docs/sdd/README.md`, `docs/WORKFLOW.md`, active/completed records under `docs/sdd/features/`.
- **Kill/defer criteria**: Stop on false `Verified` evidence, missing approval metadata, or validator/index circular drift.
- **Eval/repair signal**: `task-missing-coordination-fields`, `task-missing-agent-loop-fields`, `verified-missing-check-all`, and review defect reports.
- **Implementation**: Create the validator API and CLI with deterministic issue codes.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py -q`
- **Review owner**: parent
- **Status**: [x]

### Task 2 — Coordination board

- **File(s)**: `scripts/regen_sdd_work_index.py`, `docs/generated/sdd-work-index.md`, `tests/architecture/test_agent_playbook_contracts.py`
- **Owner**: parent
- **Depends on**: Task 1
- **Touch set**: `scripts/regen_sdd_work_index.py`, `docs/generated/sdd-work-index.md`, `tests/architecture/test_agent_playbook_contracts.py`
- **Conflict set**: `scripts/validate_sdd_artifacts.py`
- **Failing test first**: `tests/architecture/test_agent_playbook_contracts.py::test_sdd_work_index_is_generated_and_current` — asserts coordination board fields and freshness.
- **Subagent handoff**: not delegated
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `uv run python scripts/regen_sdd_work_index.py --check` must fail stale generated output.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, `docs/generated/sdd-work-index.md`, `docs/agent-playbook/task-reading-matrix.md`.
- **Kill/defer criteria**: Stop if the board duplicates parsing rules or hides active touch/conflict overlap.
- **Eval/repair signal**: stale generated index, missing factory lanes, and coordination-board review defects.
- **Implementation**: Render feature-level coordination metadata from the validator scan.
- **Verification**: `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_work_index_is_generated_and_current -q`
- **Review owner**: parent
- **Status**: [x]

### Task 3 — Test taxonomy gate

- **File(s)**: `docs/TESTING.md`, `tests/architecture/test_test_lane_contracts.py`
- **Owner**: parent
- **Depends on**: Task 1
- **Touch set**: `docs/TESTING.md`, `tests/architecture/test_test_lane_contracts.py`
- **Conflict set**: `tests/architecture`
- **Failing test first**: `tests/architecture/test_test_lane_contracts.py::test_architecture_tests_declare_harness_taxonomy` — asserts taxonomy coverage.
- **Subagent handoff**: not delegated
- **Factory lane**: Docs/contracts
- **Deterministic constraints**: Architecture tests must declare permanent invariants, migration tripwires, behavior contracts, and generated hygiene.
- **On-demand context**: `docs/TESTING.md`, `tests/architecture/test_test_lane_contracts.py`, current architecture test inventory.
- **Kill/defer criteria**: Defer broad rewrites that do not replace an overfit assertion with an explicit behavior contract.
- **Eval/repair signal**: harness taxonomy failures, expired tripwire review defects, and recurring brittle-test repair cost.
- **Implementation**: Document and enforce harness taxonomy and tripwire expiry rules.
- **Verification**: `uv run pytest tests/architecture/test_test_lane_contracts.py -q`
- **Review owner**: parent
- **Status**: [x]

### Task 4 — SQL query-contract helper and macro hard cut

- **File(s)**: `tests/support/query_contract.py`, `tests/unit/domains/macro_intel/test_macro_migration_contract.py`, `src/parallax/domains/macro_intel/repositories/macro_intel_repository.py`
- **Owner**: parent
- **Depends on**: Task 1
- **Touch set**: `tests/support/query_contract.py`, `tests/unit/domains/macro_intel/test_macro_migration_contract.py`, `src/parallax/domains/macro_intel/repositories/macro_intel_repository.py`
- **Conflict set**: `src/parallax/domains/macro_intel/runtime`, `src/parallax/domains/macro_intel/services`
- **Failing test first**: `tests/unit/domains/macro_intel/test_macro_migration_contract.py::test_repository_concept_history_counts_reads_projected_rows` — asserts request-path history counts read projected rows.
- **Subagent handoff**: not delegated
- **Factory lane**: Domain implementation
- **Deterministic constraints**: SQL contract helper must assert required and forbidden tables/predicates without alias or whitespace coupling.
- **On-demand context**: `src/parallax/domains/macro_intel/ARCHITECTURE.md`, macro repository tests, query-contract helper.
- **Kill/defer criteria**: Stop if the implementation reintroduces raw fact fallback on the request path or pins accidental SQL formatting.
- **Eval/repair signal**: SQL contract failure, macro behavior regression, and review defect on runtime truth boundary.
- **Implementation**: Add helper and update the repository to read current projected rows, not raw fact rows, for request-path counts.
- **Verification**: `uv run pytest tests/unit/domains/macro_intel/test_macro_migration_contract.py -q`
- **Review owner**: parent
- **Status**: [x]

### Task 5 — Deterministic completion gate

- **File(s)**: `Makefile`, `docs/sdd/_templates/spec-template.md`, `docs/sdd/_templates/plan-template.md`, `docs/sdd/_templates/tasks-template.md`, `docs/sdd/_templates/verification-template.md`, `docs/WORKFLOW.md`, `docs/sdd/README.md`
- **Owner**: parent
- **Depends on**: Tasks 1-4
- **Touch set**: `Makefile`, `docs/sdd/_templates`, `docs/WORKFLOW.md`, `docs/sdd/README.md`, `web/src/features/macro/ui/pages/MacroAssetOverviewPage.tsx`, `web/src/features/macro/ui/pages/MacroMatrixPage.tsx`, `web/tests/component/features/macro/MacroModulePages.test.tsx`, `web/vite.config.ts`
- **Conflict set**: `AGENTS.md`, `CLAUDE.md`
- **Failing test first**: `tests/architecture/test_agent_playbook_contracts.py::test_tasks_template_has_parallel_subagent_contract_fields` — asserts executable gate fields.
- **Subagent handoff**: not delegated; mechanical Prettier formatting added after `make check` exposed existing frontend format drift.
- **Factory lane**: Final integration
- **Deterministic constraints**: `make check-all` must include SDD validation and generated-index freshness before any `Verified` transition.
- **On-demand context**: `Makefile`, `docs/sdd/_templates`, `docs/WORKFLOW.md`, `docs/sdd/README.md`, `docs/FRONTEND.md`.
- **Kill/defer criteria**: Keep this record `In Progress` while integration/e2e/golden gates remain skipped by user instruction.
- **Eval/repair signal**: `make check-all` failure, integration skip evidence, and review defects before completion.
- **Implementation**: Wire validator into `make check-all` and update templates/docs to match the executable gate.
- **Verification**: `make check-all`
- **Review owner**: parent
- **Status**: [~]

### Task 6 — Agent factory and eval/repair loop gate

- **File(s)**: `docs/agent-playbook/factory-operating-model.md`, `docs/agent-playbook/eval-repair-loop.md`, `docs/agent-playbook/task-reading-matrix.md`, `docs/sdd/_templates/tasks-template.md`, `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_agent_playbook_contracts.py`, `tests/architecture/test_sdd_artifact_validator.py`
- **Owner**: parent
- **Depends on**: Tasks 1-5
- **Touch set**: `docs/agent-playbook`, `docs/sdd/_templates/tasks-template.md`, `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_agent_playbook_contracts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with active SDD tasks touching agent playbook docs plus SDD templates plus validator plus generated index.
- **Failing test first**: `tests/architecture/test_agent_playbook_contracts.py::test_development_agent_factory_model_is_explicit_and_bounded` and `tests/architecture/test_agent_playbook_contracts.py::test_development_agent_eval_repair_loop_is_defined` — assert explicit factory and repair-loop contracts.
- **Subagent handoff**: not delegated; current change consolidates the parent integrator contract before future lane dispatch.
- **Factory lane**: Harness/tests
- **Deterministic constraints**: New tasks must declare factory lane, deterministic constraints, on-demand context, kill/defer criteria, and eval/repair signal.
- **On-demand context**: GitHub Spec Kit model, OpenAI AGENTS/Codex loop guidance, Claude/GitHub hooks and custom-instruction separation, and `docs/AGENT_EXECUTION.md` product-agent boundary.
- **Kill/defer criteria**: Stop if a development-agent lane is confused with product LLM runtime, if more than six active lanes are implied, or if subagent output becomes authority instead of evidence.
- **Eval/repair signal**: `task-missing-agent-loop-fields`, harness failure, review defect, token cost, and missing final verification evidence.
- **Implementation**: Add factory/eval playbook docs, require new task fields, expose factory lanes in the generated work index, and validate the field set.
- **Verification**: `uv run pytest tests/architecture/test_agent_playbook_contracts.py tests/architecture/test_sdd_artifact_validator.py -q`
- **Review owner**: parent
- **Status**: [~]

## Final verification

- [ ] `uv run python scripts/validate_sdd_artifacts.py --check`
- [ ] `uv run python scripts/regen_sdd_work_index.py --check`
- [ ] `uv run pytest tests/architecture/test_sdd_artifact_validator.py tests/architecture/test_agent_playbook_contracts.py tests/architecture/test_test_lane_contracts.py -q`
- [ ] `uv run pytest tests/unit/domains/macro_intel/test_macro_migration_contract.py -q`
- [ ] `uv run pytest tests/architecture/test_agent_playbook_contracts.py tests/architecture/test_sdd_artifact_validator.py -q`
- [ ] `make check-all`
