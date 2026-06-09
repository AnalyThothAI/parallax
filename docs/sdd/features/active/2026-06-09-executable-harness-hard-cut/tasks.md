# Tasks — Executable Harness Hard Cut

**Status**: In Progress
**Owning plan**: `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut/plan.md`
**Worktree**: `.worktrees/executable-harness-hard-cut`
**Branch**: `codex/executable-harness-hard-cut`
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
- **Implementation**: Wire validator into `make check-all` and update templates/docs to match the executable gate.
- **Verification**: `make check-all`
- **Review owner**: parent
- **Status**: [~]

## Final verification

- [ ] `uv run python scripts/validate_sdd_artifacts.py --check`
- [ ] `uv run python scripts/regen_sdd_work_index.py --check`
- [ ] `uv run pytest tests/architecture/test_sdd_artifact_validator.py tests/architecture/test_agent_playbook_contracts.py tests/architecture/test_test_lane_contracts.py -q`
- [ ] `uv run pytest tests/unit/domains/macro_intel/test_macro_migration_contract.py -q`
- [ ] `make check-all`
