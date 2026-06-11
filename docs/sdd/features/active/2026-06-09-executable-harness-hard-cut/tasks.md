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
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
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
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `uv run python scripts/regen_sdd_work_index.py --check` must fail stale generated output.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, `docs/generated/sdd-work-index.md`, `docs/agent-playbook/task-reading-matrix.md`.
- **Kill/defer criteria**: Stop if the board duplicates parsing rules or hides active touch/conflict overlap.
- **Eval/repair signal**: stale generated index, missing factory lanes, and coordination-board review defects.
- **Implementation**: Render feature-level coordination metadata from the validator scan.
- **Verification**: `uv run python scripts/regen_sdd_work_index.py --check`
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
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
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
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
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
- **Conflict set**: coordinate with `2026-06-09-agent-playbook-skill-hard-cut` for shared SDD index, macro repository, and agent playbook test edits; `AGENTS.md`, `CLAUDE.md`
- **Failing test first**: `tests/architecture/test_agent_playbook_contracts.py::test_tasks_template_has_parallel_subagent_contract_fields` — asserts executable gate fields.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
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
- **Depends on**: Tasks 1-4
- **Touch set**: `docs/agent-playbook`, `docs/sdd/_templates/tasks-template.md`, `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_agent_playbook_contracts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `2026-06-09-agent-playbook-skill-hard-cut` for shared agent playbook docs plus SDD templates plus validator plus generated index.
- **Failing test first**: `tests/architecture/test_agent_playbook_contracts.py::test_development_agent_factory_model_is_explicit_and_bounded` and `tests/architecture/test_agent_playbook_contracts.py::test_development_agent_eval_repair_loop_is_defined` — assert explicit factory and repair-loop contracts.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: New tasks must declare factory lane, deterministic constraints, on-demand context, kill/defer criteria, and eval/repair signal.
- **On-demand context**: GitHub Spec Kit model, OpenAI AGENTS/Codex loop guidance, Claude/GitHub hooks and custom-instruction separation, and `docs/AGENT_EXECUTION.md` product-agent boundary.
- **Kill/defer criteria**: Stop if a development-agent lane is confused with product LLM runtime, if more than six active lanes are implied, or if subagent output becomes authority instead of evidence.
- **Eval/repair signal**: `task-missing-agent-loop-fields`, harness failure, review defect, token cost, and missing final verification evidence.
- **Implementation**: Add factory/eval playbook docs, require new task fields, expose factory lanes in the generated work index, and validate the field set.
- **Verification**: `uv run pytest tests/architecture/test_agent_playbook_contracts.py tests/architecture/test_sdd_artifact_validator.py -q`
- **Review owner**: parent
- **Status**: [x]

### Task 7 — SDD context-packet CLI

- **File(s)**: `scripts/build_agent_context_packet.py`, `docs/agent-playbook/factory-operating-model.md`, `docs/agent-playbook/task-reading-matrix.md`, `docs/agent-playbook/context-packet-template.md`, `tests/architecture/test_agent_playbook_contracts.py`
- **Owner**: parent
- **Depends on**: Task 6
- **Touch set**: `scripts/build_agent_context_packet.py`, `docs/agent-playbook/factory-operating-model.md`, `docs/agent-playbook/task-reading-matrix.md`, `docs/agent-playbook/context-packet-template.md`, `tests/architecture/test_agent_playbook_contracts.py`
- **Conflict set**: coordinate with `2026-06-09-agent-playbook-skill-hard-cut` for shared agent playbook docs and tests.
- **Failing test first**: `tests/architecture/test_agent_playbook_contracts.py::test_context_packet_cli` — asserts an executable CLI can render a bounded packet from an active SDD task.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: The CLI must run `scripts/validate_sdd_artifacts.py` semantics before emitting a packet and must reject inactive features.
- **On-demand context**: `docs/agent-playbook/context-packet-template.md`, `docs/agent-playbook/factory-operating-model.md`, active SDD task metadata.
- **Kill/defer criteria**: Stop if implementation creates product runtime queues, durable agent task state, or compatibility parsing for old planning records.
- **Eval/repair signal**: context packet CLI failure, missing active task metadata, review defect, or secret-redaction concern.
- **Implementation**: Add a filesystem-only CLI that selects one active SDD task and emits mode, lane, owned scope, conflict scope, deterministic constraints, context, kill/defer criteria, eval signal, and verification evidence.
- **Verification**: `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_context_packet_cli -q`
- **Review owner**: parent
- **Status**: [x]

### Task 8 — SDD dry-run dispatch CLI

- **File(s)**: `scripts/dispatch_sdd_task.py`, `docs/agent-playbook/factory-operating-model.md`, `docs/agent-playbook/task-reading-matrix.md`, `docs/sdd/README.md`, `tests/architecture/test_agent_playbook_contracts.py`
- **Owner**: parent
- **Depends on**: Task 7
- **Touch set**: `scripts/dispatch_sdd_task.py`, `docs/agent-playbook/factory-operating-model.md`, `docs/agent-playbook/task-reading-matrix.md`, `docs/sdd/README.md`, `tests/architecture/test_agent_playbook_contracts.py`
- **Conflict set**: coordinate with `2026-06-09-agent-playbook-skill-hard-cut` for shared agent playbook docs and tests.
- **Failing test first**: `tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_dispatch_cli_emits_handoff_for_in_progress_task` and `tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_dispatch_cli_refuses_completed_task` — assert dry-run handoff generation and completed-task refusal.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: The dispatcher must validate SDD artifacts before output and must refuse `[x]` completed tasks.
- **On-demand context**: `scripts/build_agent_context_packet.py`, `docs/agent-playbook/subagent-handoff-template.md`, active SDD task metadata.
- **Kill/defer criteria**: Stop if dispatch writes durable task state, creates product LLM queues, or bypasses context-packet generation.
- **Eval/repair signal**: dispatch CLI failure, completed-task dispatch attempt, review defect, or missing verification command.
- **Implementation**: Add a filesystem-only dry-run dispatcher that emits a subagent handoff prompt containing the generated context packet.
- **Verification**: `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_dispatch_cli_emits_handoff_for_in_progress_task tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_dispatch_cli_refuses_completed_task -q`
- **Review owner**: parent
- **Status**: [x]

### Task 9 — Task field semantic validator

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 8
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `2026-06-09-agent-playbook-skill-hard-cut` for shared SDD validator requirements and generated index.
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_tasks_reject_invalid_coordination_field_values` — asserts invalid task field values fail even when field names are present.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Validator must reject invalid task field semantics while allowing `Depends on: none` and `Subagent handoff: not delegated`.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/_templates/tasks-template.md`.
- **Kill/defer criteria**: Stop if implementation accepts `none` touch sets, non-command verification, malformed conflict rules, or unknown task statuses.
- **Eval/repair signal**: `task-invalid-coordination-fields`, validator failure, generated-index drift, and review defect.
- **Implementation**: Add `task-invalid-coordination-fields` and field-specific task validators for paths, conflict rules, command-shaped verification, test-shaped failing-test-first values, and task statuses.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_tasks_reject_invalid_coordination_field_values tests/architecture/test_sdd_artifact_validator.py::test_tasks_allow_explicit_none_dependency_and_not_delegated_handoff -q`
- **Review owner**: parent
- **Status**: [x]

### Task 10 — Verified evidence parser

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`
- **Owner**: parent
- **Depends on**: Task 9
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`
- **Conflict set**: coordinate with `2026-06-09-agent-playbook-skill-hard-cut` for shared SDD validator requirements.
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_ignores_old_success_outside_verification_commands` — asserts old successful command snippets outside `## Verification commands` do not satisfy `Verified`.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `Verified` must require the canonical `## Verification commands` fenced block to contain the single successful `make check-all` output.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, `docs/sdd/_templates/verification-template.md`, current completed SDD records.
- **Kill/defer criteria**: Stop if parser accepts stale success snippets, missing exit codes, non-zero final exit codes, or unexplained skipped tests.
- **Eval/repair signal**: `verified-missing-check-all`, `verified-contradicts-evidence`, `verified-unexplained-skips`, and review defect.
- **Implementation**: Replace broad text search with canonical section/fenced-block parsing and skipped-test table validation.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_ignores_old_success_outside_verification_commands tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_skipped_table_to_match_skip_count -q`
- **Review owner**: parent
- **Status**: [x]

### Task 11 — Task-level generated dispatch board

- **File(s)**: `scripts/regen_sdd_work_index.py`, `docs/generated/sdd-work-index.md`, `tests/architecture/test_agent_playbook_contracts.py`
- **Owner**: parent
- **Depends on**: Task 10
- **Touch set**: `scripts/regen_sdd_work_index.py`, `docs/generated/sdd-work-index.md`, `tests/architecture/test_agent_playbook_contracts.py`
- **Conflict set**: coordinate with `2026-06-09-agent-playbook-skill-hard-cut` for shared generated index and agent playbook tests.
- **Failing test first**: `tests/architecture/test_agent_playbook_contracts.py::test_sdd_work_index_renders_task_dispatch_board` — asserts the generated index renders per-task dispatch rows.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `uv run python scripts/regen_sdd_work_index.py --check` must fail stale generated task-board output.
- **On-demand context**: `scripts/regen_sdd_work_index.py`, `scripts/validate_sdd_artifacts.py`, active SDD task metadata.
- **Kill/defer criteria**: Stop if the index remains feature-only, duplicates parser rules, or hides completed/non-dispatchable task state.
- **Eval/repair signal**: stale generated index, missing `Task Board`, incorrect dispatch state, and review defect.
- **Implementation**: Add a `Task Board` section with one row per SDD task and dispatchability derived from task status and feature lane.
- **Verification**: `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_work_index_renders_task_dispatch_board -q`
- **Review owner**: parent
- **Status**: [x]

### Task 12 — Dependency-aware SDD dispatch

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `scripts/dispatch_sdd_task.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 11
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `scripts/dispatch_sdd_task.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `2026-06-09-agent-playbook-skill-hard-cut` for shared SDD validator, dispatcher, generated index, and agent playbook tests.
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_tasks_reject_unresolved_dependencies`, `tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_dispatch_cli_refuses_unmet_dependencies`, and `tests/architecture/test_agent_playbook_contracts.py::test_sdd_work_index_renders_task_dispatch_board` — assert unresolved dependencies fail validation and unmet dependencies block dispatch/index state.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Dependency parsing must be shared by validator, dispatcher, and generated index; unsupported syntax and unresolved task numbers must fail validation.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, `scripts/dispatch_sdd_task.py`, `scripts/regen_sdd_work_index.py`, active SDD task metadata.
- **Kill/defer criteria**: Stop if dispatch accepts tasks whose dependencies are not `[x]`, if the index hides dependency blocks, or if dependency parsing becomes prose-compatible magic.
- **Eval/repair signal**: `task-invalid-dependencies`, dispatcher refusal, `blocked-by-dependencies` task-board state, and review defect.
- **Implementation**: Add task dependency parsing helpers, validate unresolved dependencies, refuse unmet dependencies in dry-run dispatch, and render dependency-blocked task state.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_tasks_reject_unresolved_dependencies tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_dispatch_cli_refuses_unmet_dependencies tests/architecture/test_agent_playbook_contracts.py::test_sdd_work_index_renders_task_dispatch_board -q`
- **Review owner**: parent
- **Status**: [x]

### Task 13 — Subagent report validation gate

- **File(s)**: `scripts/validate_subagent_report.py`, `scripts/dispatch_sdd_task.py`, `docs/agent-playbook/subagent-handoff-template.md`, `docs/agent-playbook/factory-operating-model.md`, `docs/agent-playbook/eval-repair-loop.md`, `docs/sdd/README.md`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 12
- **Touch set**: `scripts/validate_subagent_report.py`, `scripts/dispatch_sdd_task.py`, `docs/agent-playbook/subagent-handoff-template.md`, `docs/agent-playbook/factory-operating-model.md`, `docs/agent-playbook/eval-repair-loop.md`, `docs/sdd/README.md`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `2026-06-09-agent-playbook-skill-hard-cut` for shared agent playbook docs, generated index, and architecture tests.
- **Failing test first**: `tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_accepts_evidence_report`, `tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_rejects_unverifiable_or_out_of_scope_report`, `tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_accepts_task_bound_report`, `tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_rejects_task_bound_scope_and_command_drift`, and `tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_dispatch_cli_emits_handoff_for_in_progress_task` — assert subagent return packets are validated against the owning SDD task before parent integration.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Returned subagent reports must have required sections, scope adherence, changed-file claims compatible with mode and task scope, expected task verification command output with exit code 0, and no secret-bearing fields.
- **On-demand context**: `docs/agent-playbook/subagent-handoff-template.md`, `docs/agent-playbook/factory-operating-model.md`, `docs/agent-playbook/eval-repair-loop.md`, `scripts/dispatch_sdd_task.py`.
- **Kill/defer criteria**: Stop if the validator accepts read-only reports with changed files, write-allowed reports outside the task touch set, conflict-set overlap, wrong verification commands, non-zero exit status, or remains only a prose checklist.
- **Eval/repair signal**: subagent report validator failure, parent review defect, missing exit-status evidence, and scope-adherence failure.
- **Implementation**: Add a filesystem-only report validator that can bind to an active SDD task and include its task-bound command in generated subagent handoffs and playbook docs.
- **Verification**: `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_accepts_evidence_report tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_rejects_unverifiable_or_out_of_scope_report tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_accepts_task_bound_report tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_rejects_task_bound_scope_and_command_drift tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_dispatch_cli_emits_handoff_for_in_progress_task -q`
- **Review owner**: parent
- **Status**: [x]

### Task 14 — Parent review outcome task state

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `docs/sdd/_templates/tasks-template.md`, `docs/agent-playbook/factory-operating-model.md`, `docs/agent-playbook/eval-repair-loop.md`, `docs/sdd/README.md`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 13
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `docs/sdd/_templates/tasks-template.md`, `docs/agent-playbook/factory-operating-model.md`, `docs/agent-playbook/eval-repair-loop.md`, `docs/sdd/README.md`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `2026-06-09-agent-playbook-skill-hard-cut` for shared generated index, SDD validator, templates, and architecture tests.
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_review_evidence_fields`, `tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_reject_invalid_review_evidence_values`, `tests/architecture/test_agent_playbook_contracts.py::test_tasks_template_has_parallel_subagent_contract_fields`, and `tests/architecture/test_agent_playbook_contracts.py::test_sdd_work_index_renders_task_dispatch_board` — assert parent review outcome is structured task state.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Validator must reject missing/inconsistent `Subagent report` and `Review result`; generated index must show report/review fields and `needs-repair` dispatch state.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `docs/sdd/_templates/tasks-template.md`, agent playbook docs.
- **Kill/defer criteria**: Stop if review outcome remains only prose, if delegated tasks can complete without accepted review evidence, or if `needs-repair` is hidden from the Task Board.
- **Eval/repair signal**: `task-missing-review-fields`, `task-invalid-review-fields`, `needs-repair` dispatch state, and parent review defects.
- **Implementation**: Add review evidence fields to templates/tasks, validate review evidence, and expose review outcome in the generated Task Board.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_review_evidence_fields tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_reject_invalid_review_evidence_values tests/architecture/test_agent_playbook_contracts.py::test_tasks_template_has_parallel_subagent_contract_fields tests/architecture/test_agent_playbook_contracts.py::test_sdd_work_index_renders_task_dispatch_board -q`
- **Review owner**: parent
- **Status**: [x]

### Task 15 — Delegated report artifact validation

- **File(s)**: `scripts/subagent_report_contract.py`, `scripts/validate_subagent_report.py`, `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 14
- **Touch set**: `scripts/subagent_report_contract.py`, `scripts/validate_subagent_report.py`, `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `2026-06-09-agent-playbook-skill-hard-cut` for shared generated index, SDD validator, and architecture tests.
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_report_artifact` and `tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_validate_report_artifact_against_task` — assert delegated task report paths are real artifacts and pass the task-bound report contract.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: SDD validation must follow delegated `Subagent report` paths and run the same task-bound report contract as the CLI without creating circular imports.
- **On-demand context**: `scripts/validate_subagent_report.py`, `scripts/validate_sdd_artifacts.py`, `scripts/subagent_report_contract.py`, active SDD task metadata.
- **Kill/defer criteria**: Stop if delegated tasks can point at missing report files, if SDD validation accepts invalid report evidence, or if the CLI and SDD validator diverge.
- **Eval/repair signal**: `task-missing-subagent-report-artifact`, `task-invalid-subagent-report-artifact`, report validator failures, and parent review defects.
- **Implementation**: Extract a shared report contract module, keep the CLI as a thin task resolver, and have SDD validation check referenced report artifacts for delegated tasks.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_report_artifact tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_validate_report_artifact_against_task tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_accepts_task_bound_report -q`
- **Review owner**: parent
- **Status**: [x]

### Task 16 — Completed task verification evidence gate

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/sdd/features/active/2026-06-09-agent-playbook-skill-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 15
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/sdd/features/active/2026-06-09-agent-playbook-skill-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `2026-06-09-agent-playbook-skill-hard-cut` for shared SDD records, generated index, and architecture fixtures.
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_complete_tasks_require_matching_verification_evidence` — asserts `[x]` tasks cannot lack matching exit-code evidence.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: SDD validation must parse `verification.md` fenced command output and require the exact task `Verification` command to have exit code 0 before `[x]` is accepted.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, active SDD task records, `docs/sdd/README.md`.
- **Kill/defer criteria**: Stop if task completion can be asserted without matching command evidence or if the gate creates self-referential task commands.
- **Eval/repair signal**: `task-complete-missing-verification-evidence`, stale generated index, and active record validation failures.
- **Implementation**: Add task-level command-evidence parsing, update index issue descriptions, and narrow self-referential task verification commands to behavior-specific gates.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_complete_tasks_require_matching_verification_evidence tests/architecture/test_agent_playbook_contracts.py::test_context_packet_cli -q`
- **Review owner**: parent
- **Status**: [x]

### Task 17 — Strict non-delegated token gate

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 16
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `2026-06-09-agent-playbook-skill-hard-cut` for shared active SDD task records and generated index.
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_non_delegated_handoff_rejects_prose_suffix` — asserts `not delegated; prose` cannot pass as a machine token.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Machine-readable task fields must use exact tokens or repo paths; rationale text belongs in narrative fields.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, active SDD task records, task template token semantics.
- **Kill/defer criteria**: Stop if a `not delegated` prefix with extra prose is accepted or if delegated repo-path handoff records are rejected.
- **Eval/repair signal**: `task-invalid-review-fields`, review defects on mixed prose/token fields, and stale generated index.
- **Implementation**: Require exact `not delegated` matching and explicit repo-path validation for delegated handoff records, then clean existing task records.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_non_delegated_handoff_rejects_prose_suffix tests/architecture/test_sdd_artifact_validator.py::test_tasks_allow_explicit_none_dependency_and_not_delegated_handoff tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_report_artifact -q`
- **Review owner**: parent
- **Status**: [x]

### Task 18 — Delegated handoff artifact validation

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/agent-playbook/factory-operating-model.md`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 17
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/agent-playbook/factory-operating-model.md`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `2026-06-09-agent-playbook-skill-hard-cut` for shared generated index and delegated-task fixtures.
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_handoff_artifact` — asserts delegated handoff paths must resolve to real artifacts.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Delegated `Subagent handoff` repo paths must exist before the validator accepts a task record.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, `docs/agent-playbook/subagent-handoff-template.md`, active SDD task records.
- **Kill/defer criteria**: Stop if a delegated task can reference a missing handoff file or if `not delegated` tasks are forced to create handoff artifacts.
- **Eval/repair signal**: `task-missing-subagent-handoff-artifact`, stale generated index, and parent review defects.
- **Implementation**: Add handoff artifact existence validation alongside report artifact validation and expose the new issue code in the generated index.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_handoff_artifact tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_report_artifact -q`
- **Review owner**: parent
- **Status**: [x]

### Task 19 — Artifact lifecycle status consistency gate

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 18
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `2026-06-09-agent-playbook-skill-hard-cut` for shared SDD lifecycle records and generated index.
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_feature_rejects_mixed_artifact_statuses` — asserts mixed artifact lifecycle statuses cannot pass.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Every present SDD artifact in a feature must declare the same `Status` before lifecycle gates trust the feature state.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, active and completed SDD feature records, generated SDD work index.
- **Kill/defer criteria**: Stop if a mixed `Verified`/`Superseded` or active/completed status set can pass validation.
- **Eval/repair signal**: `artifact-status-mismatch`, stale generated index, and lifecycle review defects.
- **Implementation**: Add feature-level artifact status mismatch validation and expose the issue code in the generated index.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_feature_rejects_mixed_artifact_statuses -q`
- **Review owner**: parent
- **Status**: [x]

### Task 20 — Machine-readable superseded successor gate

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/WORKFLOW.md`, `docs/sdd/README.md`, `docs/sdd/_templates`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 19
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/WORKFLOW.md`, `docs/sdd/README.md`, `docs/sdd/_templates`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `2026-06-09-agent-playbook-skill-hard-cut` for shared SDD lifecycle docs, templates, validator, and generated index.
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_superseded_feature_requires_machine_readable_successor` — asserts prose-only successor mentions cannot pass.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: A `Superseded` artifact must use `**Superseded by**` metadata with an existing repo path to the successor SDD record.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, completed SDD feature records, SDD templates, `docs/WORKFLOW.md`.
- **Kill/defer criteria**: Stop if prose-only successor text, non-path values, or missing successor paths can pass validation.
- **Eval/repair signal**: `superseded-missing-successor`, stale generated index, and docs/source drift review defects.
- **Implementation**: Require machine-readable successor metadata for superseded artifacts, document the field, and expose the stronger lifecycle flag meaning.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_superseded_feature_requires_machine_readable_successor -q`
- **Review owner**: parent
- **Status**: [x]

### Task 21 — Exact four-artifact feature directory gate

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/WORKFLOW.md`, `docs/sdd/README.md`, `docs/sdd/_templates/README.md`, `docs/sdd/features/completed/2026-06-09-macro-intel-redesign`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 20
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/WORKFLOW.md`, `docs/sdd/README.md`, `docs/sdd/_templates/README.md`, `docs/sdd/features/completed/2026-06-09-macro-intel-redesign`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `2026-06-09-agent-playbook-skill-hard-cut` for shared SDD lifecycle docs, validator, generated index, and completed-record cleanup.
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_feature_rejects_unexpected_artifact_files` — asserts extra feature files cannot pass.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: SDD feature directories must contain exactly `spec.md`, `plan.md`, `tasks.md`, and `verification.md`; old screenshots, mockups, logs, and notes are not allowed.
- **On-demand context**: `docs/sdd/README.md`, `docs/WORKFLOW.md`, completed SDD records, generated work index.
- **Kill/defer criteria**: Stop if validator ignores extra feature files or if existing completed records retain local attachments.
- **Eval/repair signal**: `unexpected-artifact`, stale generated index, dangling old-file references, and docs/source drift review defects.
- **Implementation**: Add unexpected-artifact validation, remove old macro SDD attachments, clean dangling references, and expose the issue in docs/index.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_feature_rejects_unexpected_artifact_files -q`
- **Review owner**: parent
- **Status**: [x]

### Task 22 — Completed task dependency completion gate

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 21
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `2026-06-09-agent-playbook-skill-hard-cut` for shared SDD task dependency semantics and generated index.
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_completed_tasks_reject_incomplete_dependencies` — asserts `[x]` tasks cannot depend on incomplete tasks.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: A completed task's declared dependencies must all exist and be `[x]`; incomplete prerequisites keep completion invalid.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, active SDD task records.
- **Kill/defer criteria**: Stop if a completed task can depend on an incomplete task or if Task 5 is marked complete without final `make check-all`.
- **Eval/repair signal**: `task-invalid-dependencies`, stale generated index, and task-board dispatch state drift.
- **Implementation**: Reuse dependency parsing to reject completed tasks with incomplete prerequisites and correct Task 6's dependency to the actually completed harness foundation.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_completed_tasks_reject_incomplete_dependencies -q`
- **Review owner**: parent
- **Status**: [x]

### Task 23 — Completed task evidence section gate

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 22
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `2026-06-09-agent-playbook-skill-hard-cut` for shared SDD verification semantics and generated index.
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_complete_task_evidence_ignores_commands_outside_evidence_sections` — asserts Notes code blocks do not satisfy completed-task evidence.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Completed-task command evidence must appear in `## Verification commands` or `## Other commands run`, not arbitrary fenced blocks.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, active SDD verification records.
- **Kill/defer criteria**: Stop if stale examples or notes can satisfy completed-task evidence.
- **Eval/repair signal**: `task-complete-missing-verification-evidence`, false-positive command evidence, and stale generated index.
- **Implementation**: Restrict completed-task command evidence parsing to canonical evidence sections and add a Notes-block regression test.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_complete_task_evidence_ignores_commands_outside_evidence_sections -q`
- **Review owner**: parent
- **Status**: [x]

### Task 24 — Superseded metadata hard gate

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/completed`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 23
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/completed`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `2026-06-09-agent-playbook-skill-hard-cut` for shared SDD lifecycle semantics and completed-record metadata.
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_superseded_feature_requires_approval_metadata` — asserts `Superseded` artifacts still require approval metadata.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Superseded records may skip content-section gates, but must still carry required status, date/worktree/branch, approval, and successor metadata.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, completed SDD feature records, SDD lifecycle docs.
- **Kill/defer criteria**: Stop if old completed records can omit approval metadata or if superseded records are forced to claim fresh verification.
- **Eval/repair signal**: `missing-approval-metadata`, completed-record drift, and stale generated index.
- **Implementation**: Move metadata validation before the Superseded content-section early return and backfill completed SDD artifact metadata.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_superseded_feature_requires_approval_metadata -q`
- **Review owner**: parent
- **Status**: [x]

### Task 25 — Superseded structured task record gate

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/completed/2026-06-09-sdd-governance-hard-cut/tasks.md`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 24
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/completed/2026-06-09-sdd-governance-hard-cut/tasks.md`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `2026-06-09-agent-playbook-skill-hard-cut` for shared SDD lifecycle semantics and completed-record task structure.
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_superseded_feature_requires_structured_tasks` — asserts legacy checkbox-only tasks cannot pass as Superseded.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Superseded `tasks.md` may skip full active-task field validation, but must still retain structured `### Task` records.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, completed SDD feature records, SDD task templates.
- **Kill/defer criteria**: Stop if completed records need a checkbox-only compatibility format or if old tasks cannot be mapped to structured records.
- **Eval/repair signal**: `task-missing-coordination-fields`, stale generated index, and completed-record drift.
- **Implementation**: Add a Superseded structured-task check and convert the legacy governance completed tasks record into structured tasks.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_superseded_feature_requires_structured_tasks -q`
- **Review owner**: parent
- **Status**: [x]

### Task 26 — Superseded successor consistency gate

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 25
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `2026-06-09-agent-playbook-skill-hard-cut` for shared SDD lifecycle semantics and generated index.
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_superseded_feature_requires_one_successor` — asserts one `Superseded` feature cannot split successor paths.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Superseded artifacts in one feature must agree on one existing successor path.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, completed SDD feature records, generated SDD work index.
- **Kill/defer criteria**: Stop if split successor paths can pass validation or if current completed records disagree on successors.
- **Eval/repair signal**: `superseded-successor-mismatch`, stale generated index, and lifecycle drift.
- **Implementation**: Collect valid successor paths across all superseded artifacts in a feature and reject multiple values.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_superseded_feature_requires_one_successor -q`
- **Review owner**: parent
- **Status**: [x]

### Task 27 — Completed task review outcome gate

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 26
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `2026-06-09-agent-playbook-skill-hard-cut` for shared task review semantics and generated index.
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_complete_tasks_require_review_result_evidence` — asserts `[x]` tasks cannot keep `Review result: not delegated`.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Completed tasks must carry explicit `parent-reviewed` or `accepted` review outcome evidence.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, active SDD task records, generated SDD work index.
- **Kill/defer criteria**: Stop if a completed task can pass with only `not delegated` as its review result.
- **Eval/repair signal**: `task-complete-missing-review-evidence`, stale generated index, and review-loop drift.
- **Implementation**: Add a completed-task review-evidence issue code and reject `[x]` tasks without a real review outcome.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_complete_tasks_require_review_result_evidence -q`
- **Review owner**: parent
- **Status**: [x]

### Task 28 — Task DAG numbering gate

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 27
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `2026-06-09-agent-playbook-skill-hard-cut` for shared task dependency and dispatch semantics.
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_tasks_require_unique_contiguous_numbers` — asserts duplicate or skipped task numbers cannot pass.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Structured task headings must form one unique contiguous `Task 1..N` DAG before dispatch/dependency state is trusted.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, active and completed SDD task records, generated SDD work index.
- **Kill/defer criteria**: Stop if duplicate, skipped, or unnumbered task headings can pass validation.
- **Eval/repair signal**: `task-invalid-numbering`, stale generated index, and dispatch graph drift.
- **Implementation**: Validate machine-readable task numbers before per-task dependency checks and expose the issue in the generated lifecycle flags.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_tasks_require_unique_contiguous_numbers -q`
- **Review owner**: parent
- **Status**: [x]

### Task 29 — Artifact owning-link lineage gate

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 28
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `2026-06-09-agent-playbook-skill-hard-cut` for shared SDD lineage metadata and generated index.
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_artifact_owning_links_must_point_to_same_feature` — asserts cross-feature owning links cannot pass.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `Owning spec` and `Owning plan` metadata must point at the same feature's canonical `spec.md` and `plan.md` files.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, active and completed SDD artifacts, generated SDD work index.
- **Kill/defer criteria**: Stop if old feature links or arbitrary existing paths can satisfy current feature lineage metadata.
- **Eval/repair signal**: `artifact-owning-link-mismatch`, stale generated index, and Spec→Plan→Tasks→Verification drift.
- **Implementation**: Validate artifact owning-link metadata against the feature-relative canonical paths and expose the issue in lifecycle flags.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_artifact_owning_links_must_point_to_same_feature -q`
- **Review owner**: parent
- **Status**: [x]

### Task 30 — Acceptance command coverage gate

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 29
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `2026-06-09-agent-playbook-skill-hard-cut` for shared SDD acceptance-command semantics and generated index.
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_plan_acceptance_commands_must_cover_spec_acceptance_criteria` — asserts spec ACs cannot lack plan command coverage.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Non-superseded feature specs and plans must have an exact AC-number match between spec criteria and plan acceptance commands.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, active SDD spec/plan artifacts, generated SDD work index.
- **Kill/defer criteria**: Stop if a spec criterion can pass without an executable plan command or if plan declares phantom AC commands.
- **Eval/repair signal**: `acceptance-command-mismatch`, stale generated index, and Spec→Plan coverage drift.
- **Implementation**: Parse spec AC headings and plan `- ACx:` command entries, then reject missing or extra command mappings.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_plan_acceptance_commands_must_cover_spec_acceptance_criteria -q`
- **Review owner**: parent
- **Status**: [x]

### Task 31 — Acceptance numbering gate

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 30
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `2026-06-09-agent-playbook-skill-hard-cut` for shared SDD acceptance-command semantics and generated index.
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_acceptance_criteria_and_commands_require_contiguous_numbers` — asserts synchronized AC gaps cannot pass.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Spec criteria and plan command entries must each form one unique contiguous `AC1..N` sequence.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, active SDD spec/plan artifacts, generated SDD work index.
- **Kill/defer criteria**: Stop if spec and plan can agree on skipped, duplicate, or reordered AC numbers.
- **Eval/repair signal**: `acceptance-numbering-invalid`, stale generated index, and Spec→Plan coverage drift.
- **Implementation**: Preserve AC number order while parsing spec and plan, then reject non-contiguous sequences before coverage comparison.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_acceptance_criteria_and_commands_require_contiguous_numbers -q`
- **Review owner**: parent
- **Status**: [x]

### Task 32 — Acceptance command shape gate

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 31
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `2026-06-09-agent-playbook-skill-hard-cut` for shared SDD acceptance-command semantics and generated index.
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_plan_acceptance_commands_must_be_command_shaped` — asserts prose AC commands cannot pass.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Plan acceptance command entries must be command-shaped before they count as AC coverage.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, active SDD plan artifacts, generated SDD work index.
- **Kill/defer criteria**: Stop if backticked prose such as `read the docs` can satisfy plan AC command coverage.
- **Eval/repair signal**: `acceptance-command-invalid`, stale generated index, and Spec→Plan coverage drift.
- **Implementation**: Parse plan AC command text, reject entries that do not pass the existing command-shape predicate, and expose the issue in lifecycle flags.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_plan_acceptance_commands_must_be_command_shaped -q`
- **Review owner**: parent
- **Status**: [x]

### Task 33 — Acceptance command exact-line gate

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 32
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `2026-06-09-agent-playbook-skill-hard-cut` for shared SDD acceptance-command semantics and generated index.
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_plan_acceptance_commands_reject_trailing_prose` — asserts command-line escape prose cannot pass.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Acceptance command bullets must be exact `ACn` command lines with no trailing prose, ranges, or side labels.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, active SDD plan artifacts, generated SDD work index, Carver read-only audit.
- **Kill/defer criteria**: Stop if `or equivalent`, `AC1-AC2`, or non-AC command labels can survive inside `## Acceptance test commands`.
- **Eval/repair signal**: `acceptance-command-invalid`, stale generated index, and plan execution drift.
- **Implementation**: Anchor plan AC command parsing to full lines and reject nonmatching bullets inside the acceptance command section.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_plan_acceptance_commands_reject_trailing_prose -q`
- **Review owner**: parent
- **Status**: [x]

### Task 34 — Feature slug/date identity gate

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 33
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `2026-06-09-agent-playbook-skill-hard-cut` for shared SDD lifecycle flags and generated index.
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_feature_directory_name_and_date_metadata_are_machine_valid` — asserts freeform feature slugs and date drift cannot pass.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Feature directories must match `YYYY-MM-DD-kebab-slug`, and artifact `Date` fields must match the slug date.
- **On-demand context**: `docs/WORKFLOW.md`, `docs/sdd/README.md`, `docs/sdd/_templates/README.md`, Carver read-only audit.
- **Kill/defer criteria**: Stop if old/freeform planning names can pass as current SDD feature records.
- **Eval/repair signal**: `feature-slug-invalid`, stale generated index, and old-lane drift.
- **Implementation**: Add a feature identity validator and generated-index lifecycle meaning for invalid slugs/date metadata.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_feature_directory_name_and_date_metadata_are_machine_valid -q`
- **Review owner**: parent
- **Status**: [x]

### Task 35 — Gate evidence row validator

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 34
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `2026-06-09-agent-playbook-skill-hard-cut` for shared SDD gate semantics and generated index.
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_gate_sections_require_non_placeholder_evidence` — asserts empty copied gate tables cannot pass.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Required clarify, checklist, analyze, and gate-compliance sections must include at least one non-placeholder table row.
- **On-demand context**: `docs/WORKFLOW.md`, `docs/sdd/_templates`, Carver read-only audit.
- **Kill/defer criteria**: Stop if section headings or blank template rows can satisfy clarify/checklist/analyze gate requirements.
- **Eval/repair signal**: `gate-evidence-missing`, stale generated index, and copied-template drift.
- **Implementation**: Parse required gate tables and reject sections that contain no non-placeholder evidence row.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_sections_require_non_placeholder_evidence -q`
- **Review owner**: parent
- **Status**: [x]

### Task 36 — Acceptance criterion format gate

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 35
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `2026-06-09-agent-playbook-skill-hard-cut` for shared SDD acceptance semantics and generated index.
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_acceptance_criteria_require_when_then_shall_format` — asserts vague AC prose cannot pass.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Spec acceptance criteria must use machine-readable `WHEN ... THEN ... SHALL ...` structure before plan-command coverage is trusted.
- **On-demand context**: `docs/sdd/_templates/spec-template.md`, Carver read-only audit, active SDD specs.
- **Kill/defer criteria**: Stop if vague AC prose can be numbered and covered by a plan command.
- **Eval/repair signal**: `acceptance-criterion-format-invalid`, stale generated index, and Spec→Plan coverage drift.
- **Implementation**: Parse full AC lines and reject criteria that lack the executable WHEN/THEN/SHALL structure.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_acceptance_criteria_require_when_then_shall_format -q`
- **Review owner**: parent
- **Status**: [x]

### Task 37 — Verified spec-compliance evidence gate

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 36
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `2026-06-09-agent-playbook-skill-hard-cut` for shared SDD verification semantics and generated index.
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_verified_spec_compliance_rows_require_matching_command_evidence` — asserts a Verified compliance row cannot cite an unproven command.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Verified Spec compliance table rows that mark criteria complete must cite only command evidence that has exit code 0 in `## Verification commands` or `## Other commands run`.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, active/completed SDD verification records, generated SDD work index.
- **Kill/defer criteria**: Stop if a Verified record can mark an acceptance row complete while the cited command is missing or failed in canonical evidence sections.
- **Eval/repair signal**: `verified-missing-spec-compliance-evidence`, stale generated index, and false-green verification drift.
- **Implementation**: Parse completed Spec compliance rows, extract command-shaped backticked evidence references, and require matching exit code 0 command evidence.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_spec_compliance_rows_require_matching_command_evidence -q`
- **Review owner**: parent
- **Status**: [x]

### Task 38 — Worktree metadata hard cut

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/sdd/features/active/2026-06-09-agent-playbook-skill-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 37
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/sdd/features/active/2026-06-09-agent-playbook-skill-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `2026-06-09-agent-playbook-skill-hard-cut` for shared Worktree/Branch metadata and generated index.
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_worktree_branch_metadata_must_be_machine_valid` — asserts template placeholders and branch/worktree mismatches cannot pass.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Worktree/Branch metadata must be either `codex/<slug>` with `.worktrees/<slug>` across plan/tasks/verification or the exact `main`/`main` machine token pair.
- **On-demand context**: Banach read-only audit, `docs/WORKFLOW.md`, active SDD feature metadata, generated SDD work index.
- **Kill/defer criteria**: Stop if copied template placeholders, prose execution-location values, or cross-artifact branch/worktree disagreement can pass validation.
- **Eval/repair signal**: `worktree-metadata-invalid`, stale generated index, and old metadata drift.
- **Implementation**: Add strict Worktree/Branch metadata parsing, expose the issue code, and convert the agent-playbook active record from prose Worktree metadata to `main`.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_worktree_branch_metadata_must_be_machine_valid -q`
- **Review owner**: parent
- **Status**: [x]

### Task 39 — Source-backed spec background gate

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/sdd/features/active/2026-06-09-agent-playbook-skill-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 38
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/sdd/features/active/2026-06-09-agent-playbook-skill-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `2026-06-09-agent-playbook-skill-hard-cut` for shared SDD background/source citations.
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_spec_background_requires_source_citations` — asserts uncited Background claims cannot pass.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Each non-superseded spec Background claim block must cite an existing repo `path:line` or external `https://` source; local path citations must resolve to existing files and in-range line numbers.
- **On-demand context**: GitHub Spec Kit, OpenAI agent eval/Codex guidance, Claude hooks/subagents docs, GitHub Copilot task best practices, active SDD specs.
- **Kill/defer criteria**: Stop if a spec can describe current behavior or external methodology without auditable source evidence.
- **Eval/repair signal**: `spec-background-uncited`, stale generated index, and source drift review defects.
- **Implementation**: Parse Background claim blocks, validate local repo line citations, accept external HTTPS sources, and backfill active specs with current local/external references.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_spec_background_requires_source_citations -q`
- **Review owner**: parent
- **Status**: [x]

### Task 40 — Plan pre-flight metadata gate

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 39
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `2026-06-09-agent-playbook-skill-hard-cut` for shared Worktree/Branch metadata.
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_plan_preflight_worktree_claims_must_match_metadata` — asserts checked Pre-flight setup evidence cannot cite stale Worktree/Branch values.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: A checked `plan.md` Pre-flight row that claims Worktree/Branch verification must match the same artifact's machine-readable Worktree and Branch metadata.
- **On-demand context**: `docs/WORKFLOW.md`, active SDD plan records, generated SDD work index.
- **Kill/defer criteria**: Stop if stale checked setup evidence can survive after Worktree/Branch metadata changes.
- **Eval/repair signal**: `plan-preflight-metadata-mismatch`, stale generated index, and setup-evidence drift.
- **Implementation**: Parse checked Worktree/Branch Pre-flight rows, compare them to plan metadata, and correct the active executable-harness pre-flight claim.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_plan_preflight_worktree_claims_must_match_metadata -q`
- **Review owner**: parent
- **Status**: [x]

### Task 41 — Subagent handoff artifact binding gate

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 40
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `2026-06-09-agent-playbook-skill-hard-cut` for shared subagent handoff/report semantics.
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_validate_handoff_artifact_against_task` — asserts an existing handoff artifact from another feature/task cannot satisfy delegated task evidence.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Delegated `Subagent handoff` artifacts must name the same feature and task in the handoff title, embedded context packet, Mode line, and report-validation command.
- **On-demand context**: `docs/agent-playbook/factory-operating-model.md`, `docs/agent-playbook/subagent-handoff-template.md`, `scripts/dispatch_sdd_task.py`.
- **Kill/defer criteria**: Stop if a stale or wrong-task handoff file can pass because it merely exists.
- **Eval/repair signal**: `task-invalid-subagent-handoff-artifact`, stale generated index, and parent review defects from wrong handoff context.
- **Implementation**: Parse delegated handoff artifacts and reject stale feature/task/mode/report-validator bindings before accepting the task record.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_validate_handoff_artifact_against_task -q`
- **Review owner**: parent
- **Status**: [x]

### Task 42 — Subagent report mode binding gate

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 41
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `2026-06-09-agent-playbook-skill-hard-cut` for shared subagent report semantics.
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_delegated_report_mode_must_match_handoff_mode` — asserts a report cannot claim `write-allowed` when the handoff granted `read-only`.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Delegated reports must be validated with the owning handoff mode; report-authored `Mode:` is evidence to check, not authority to choose scope.
- **On-demand context**: `scripts/subagent_report_contract.py`, `scripts/validate_sdd_artifacts.py`, `docs/agent-playbook/factory-operating-model.md`.
- **Kill/defer criteria**: Stop if a subagent report can broaden dispatch scope by changing its own `Mode:` line.
- **Eval/repair signal**: `task-invalid-subagent-report-artifact`, scope-adherence failures, and parent review defects from mode drift.
- **Implementation**: Parse delegated handoff mode and pass it to the existing subagent report validator instead of trusting the report's self-declared mode.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_delegated_report_mode_must_match_handoff_mode -q`
- **Review owner**: parent
- **Status**: [x]

### Task 43 — Factory lane enum gate

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 42
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `2026-06-09-agent-playbook-skill-hard-cut` for shared factory-lane semantics.
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_tasks_reject_invalid_factory_lane_values` — asserts freeform or compatibility lane names cannot pass task validation.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `Factory lane` must be one of `Spec/plan`, `Domain implementation`, `Harness/tests`, `Docs/contracts`, `Risk radar`, or `Final integration`.
- **On-demand context**: `docs/agent-playbook/factory-operating-model.md`, active `tasks.md` records, generated SDD work index.
- **Kill/defer criteria**: Stop if old/freeform lane names such as `Harness/docs` or `Compatibility` can pass validation.
- **Eval/repair signal**: `task-invalid-agent-loop-fields`, stale generated index, and lane-budget drift.
- **Implementation**: Add a validator enum for factory lanes, report invalid agent-loop fields, migrate current active task records to table-defined lane tokens, and refresh the generated index.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_tasks_reject_invalid_factory_lane_values -q`
- **Review owner**: parent
- **Status**: [x]

### Task 44 — Analyze gate result token gate

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/_templates/plan-template.md`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/sdd/features/active/2026-06-09-agent-playbook-skill-hard-cut/plan.md`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 43
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/_templates/plan-template.md`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/sdd/features/active/2026-06-09-agent-playbook-skill-hard-cut/plan.md`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `2026-06-09-agent-playbook-skill-hard-cut` for shared Analyze Gate status semantics.
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_plan_analyze_gate_rejects_failed_results` — asserts `Fail:` Analyze Gate rows cannot pass as implementation-ready evidence.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `plan.md` Analyze Gate result cells must begin with `Pass:` or `Blocked:`; failed analysis must stop or block the feature before implementation.
- **On-demand context**: GitHub Spec Kit analyze gate semantics, `docs/sdd/_templates/plan-template.md`, active plan records.
- **Kill/defer criteria**: Stop if `Fail:`, `Pass.`, or other freeform Analyze Gate results can satisfy planning evidence.
- **Eval/repair signal**: `plan-analyze-gate-invalid`, stale generated index, and analyze-gate drift.
- **Implementation**: Validate Analyze Gate result tokens, update the plan template to show `Pass:` evidence, and migrate current active plans to machine-statused results.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_plan_analyze_gate_rejects_failed_results -q`
- **Review owner**: parent
- **Status**: [x]

### Task 45 — Completed task failing-test evidence gate

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 44
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `2026-06-09-agent-playbook-skill-hard-cut` for shared SDD validator semantics and generated index.
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_complete_tasks_require_failing_test_reference_evidence` — asserts completed tasks cannot declare a failing-test reference that has no successful verification evidence.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Completed tasks must have successful command evidence covering every test file path declared in `Failing test first`; exact historical RED failure output is not required or fabricated.
- **On-demand context**: TDD discipline, active SDD task records, `verification.md` canonical evidence sections, and generated SDD work index.
- **Kill/defer criteria**: Stop if completed tasks can satisfy TDD metadata with unrelated commands or if the validator requires non-existent historical RED logs.
- **Eval/repair signal**: `task-complete-missing-failing-test-evidence`, stale generated index, and review defects around unproven TDD claims.
- **Implementation**: Parse test file paths from `Failing test first`, compare them to successful command evidence in `verification.md`, expose the issue code in the generated index, and record AC45 evidence.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_complete_tasks_require_failing_test_reference_evidence -q`
- **Review owner**: parent
- **Status**: [x]

### Task 46 — Generated CLI help freshness gate

- **File(s)**: `Makefile`, `scripts/regen_cli_help.py`, `tests/architecture/test_harness_structure.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 45
- **Touch set**: `Makefile`, `scripts/regen_cli_help.py`, `tests/architecture/test_harness_structure.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `2026-06-09-agent-playbook-skill-hard-cut` for shared SDD index and completion-gate semantics.
- **Failing test first**: `tests/architecture/test_harness_structure.py::test_make_check_all_checks_cli_help_snapshot` — asserts `check-all` runs the generated CLI help freshness check.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: CLI help freshness must be checked by a non-mutating `--check` command before integration/e2e/golden/coverage gates; no database-backed docs regeneration is introduced into the fast harness stage.
- **On-demand context**: `scripts/regen_cli_help.py`, `docs/generated/cli-help.md`, `Makefile`, `docs/generated/README.md`, and `docs/ARCHITECTURE.md`.
- **Kill/defer criteria**: Stop if the gate mutates generated files during verification, depends on PostgreSQL, or leaves CLI warning output in normal successful checks.
- **Eval/repair signal**: stale CLI help snapshot, `test_make_check_all_checks_cli_help_snapshot` failure, and `scripts/regen_cli_help.py --check` non-zero exit.
- **Implementation**: Add `--check` to the CLI help generator, wire it into `make check-all`, and prove the Makefile gate with an architecture test.
- **Verification**: `uv run pytest tests/architecture/test_harness_structure.py::test_make_check_all_checks_cli_help_snapshot -q`
- **Review owner**: parent
- **Status**: [x]

### Task 47 — Public contracts source-alignment gate

- **File(s)**: `docs/CONTRACTS.md`, `tests/architecture/test_public_contracts_doc_alignment.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 46
- **Touch set**: `docs/CONTRACTS.md`, `tests/architecture/test_public_contracts_doc_alignment.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `docs/CONTRACTS.md` for shared News route and WebSocket payload semantics.
- **Failing test first**: `tests/architecture/test_public_contracts_doc_alignment.py::test_contracts_worker_keys_match_manifest_registry` — asserts public runtime contract docs cannot list retired worker keys; the same file covers stale agent lanes, removed WS payload keys, and the old News item detail route.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Docs/contracts
- **Deterministic constraints**: Contract docs must be checked against `WorkerManifest`, `WorkersSettings`, `ws.py`, and `routes_news.py`; no compatibility wording for retired worker keys or old routes.
- **On-demand context**: Explorer audit of `docs/CONTRACTS.md`, `docs/WORKERS.md`, `src/parallax/app/runtime/worker_manifest.py`, `src/parallax/platform/config/settings.py`, and API route source.
- **Kill/defer criteria**: Stop if the test merely bans words without binding to source, or if docs keep duplicate stale lists that can drift from runtime code.
- **Eval/repair signal**: `test_public_contracts_doc_alignment.py` failures, source/doc drift in public runtime contracts, and review defects around stale public API wording.
- **Implementation**: Add source-bound architecture tests, update `CONTRACTS.md` to current worker keys, agent lanes, WS payloads, and News item route, and refresh the generated SDD index.
- **Verification**: `uv run pytest tests/architecture/test_public_contracts_doc_alignment.py -q`
- **Review owner**: parent
- **Status**: [x]

### Task 48 — Generated README source-map gate

- **File(s)**: `docs/generated/README.md`, `scripts/regen_ws_protocol.py`, `tests/architecture/test_harness_structure.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 47
- **Touch set**: `docs/generated/README.md`, `scripts/regen_ws_protocol.py`, `tests/architecture/test_harness_structure.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `docs/generated/README.md` for generated docs source-map semantics.
- **Failing test first**: `tests/architecture/test_harness_structure.py::test_generated_readme_source_map_points_to_existing_paths` — asserts generated-doc source-map rows cannot point at retired or missing source paths.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Docs/contracts
- **Deterministic constraints**: Generated README rows must name existing generated files, generator scripts, and backticked source paths; do not depend on database-backed docs regeneration for this fast architecture check.
- **On-demand context**: `docs/generated/README.md`, `scripts/regen_ws_protocol.py`, `docs/generated/ws-protocol.md`, and `Makefile` docs-generated targets.
- **Kill/defer criteria**: Stop if the check becomes a prose wording lock instead of path existence/source-map validation, or if it requires integration/database setup.
- **Eval/repair signal**: missing generated file, missing generator script, stale source path, `test_generated_readme_source_map_points_to_existing_paths` failure, and generated-doc review defects.
- **Implementation**: Add a path-backed generated README source-map architecture test, update the stale WebSocket source pointer, and align the WebSocket protocol generator docstring.
- **Verification**: `uv run pytest tests/architecture/test_harness_structure.py::test_generated_readme_source_map_points_to_existing_paths -q`
- **Review owner**: parent
- **Status**: [x]

### Task 49 — Active touch conflict path-awareness gate

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 48
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `2026-06-09-agent-playbook-skill-hard-cut` for shared SDD validator conflict semantics and generated index.
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_active_touch_sets_reject_nested_or_misdirected_coordination` — asserts nested touch-set overlaps and unrelated coordination prose still fail.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Active touch overlap detection must normalize repo paths, catch exact and parent/child path overlaps, and only suppress conflicts when coordination names the overlapping feature slug or path.
- **On-demand context**: SDD explorer report, `docs/WORKFLOW.md`, `docs/agent-playbook/factory-operating-model.md`, validator active conflict implementation, and SDD fixture tests.
- **Kill/defer criteria**: Stop if the rule allows unrelated `coordinate` prose, misses nested paths, or floods current valid active records with false positives.
- **Eval/repair signal**: `active-touch-conflict` issue coverage, SDD validator failure, generated-index drift, and multi-agent touch-set review defects.
- **Implementation**: Add RED fixture for parent/child touch overlap with misdirected coordination, update active conflict detection to normalize/compare nested paths, and require targeted coordination.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_active_touch_sets_reject_nested_or_misdirected_coordination -q`
- **Review owner**: parent
- **Status**: [x]

### Task 50 — Frontend docs and skill source-alignment gate

- **File(s)**: `docs/FRONTEND.md`, `.agents/skills/parallax-frontend-verification/SKILL.md`, `web/tests/architecture/frontendDocContract.test.ts`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 49
- **Touch set**: `docs/FRONTEND.md`, `.agents/skills/parallax-frontend-verification/SKILL.md`, `web/tests/architecture/frontendDocContract.test.ts`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `docs/FRONTEND.md` for frontend architecture documentation and skill semantics.
- **Failing test first**: `tests/architecture/frontendDocContract.test.ts::frontend documentation contract` — asserts frontend docs and skill cannot drift from CSS architecture constants, shell entrypoint policy, or app navigation source under the `web/` test command.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Docs/contracts
- **Deterministic constraints**: Frontend docs and skill must name the retired CSS buckets from `cssArchitectureHarness.test.ts`, the 500-line side-effect CSS budget from `cssResponsiveContract.test.ts`, sanctioned `@features/<name>/shell` entrypoints, and drawer routes present in `APP_NAVIGATION_GROUPS`.
- **On-demand context**: Frontend explorer report, `docs/FRONTEND.md`, `.agents/skills/parallax-frontend-verification/SKILL.md`, frontend architecture tests, and `web/src/features/cockpit/ui/appNavigation.ts`.
- **Kill/defer criteria**: Stop if the gate freezes cosmetic prose rather than source-backed constants/routes, or if it requires browser/e2e execution.
- **Eval/repair signal**: frontend doc-contract failures, stale retired CSS bucket wording, stale side-effect CSS budget, stale frontend skill commands, and route-shell review defects.
- **Implementation**: Add a static frontend doc-contract architecture test and update FRONTEND docs plus the frontend verification skill to current harness/source truth.
- **Verification**: `cd web && npm run test -- tests/architecture/frontendDocContract.test.ts`
- **Review owner**: parent
- **Status**: [x]

### Task 51 — Frontend feature-boundary root derivation gate

- **File(s)**: `web/tests/architecture/featureBoundaries.test.ts`, `docs/FRONTEND.md`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 50
- **Touch set**: `web/tests/architecture/featureBoundaries.test.ts`, `docs/FRONTEND.md`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `docs/FRONTEND.md` for frontend architecture documentation and boundary semantics.
- **Failing test first**: `tests/architecture/featureBoundaries.test.ts::feature boundaries` — asserts the relative-import boundary scan cannot omit current feature roots or keep removed roots under the `web/` test command.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Feature-boundary scans must derive feature roots from `web/src/features`, escape feature names before building regexes, and continue scanning production feature source for relative imports into another feature's internals.
- **On-demand context**: Frontend explorer report, `web/tests/architecture/featureBoundaries.test.ts`, `web/src/features`, `docs/FRONTEND.md`, and frontend architecture test output.
- **Kill/defer criteria**: Stop if implementation hard-codes the current feature list, scans test fixtures as production boundaries, or weakens deep-import detection to hide existing violations.
- **Eval/repair signal**: omitted feature root, removed feature root still scanned, frontend boundary architecture failure, and deep-import review defects.
- **Implementation**: Add RED coverage for stale feature-name lists, replace the hard-coded regex with source-derived feature roots, and document the source-derived boundary gate.
- **Verification**: `cd web && npm run test -- tests/architecture/featureBoundaries.test.ts`
- **Review owner**: parent
- **Status**: [x]

### Task 52 — Frontend data ownership architecture gate

- **File(s)**: `web/tests/architecture/frontendDataOwnership.test.ts`, `docs/FRONTEND.md`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 51
- **Touch set**: `web/tests/architecture/frontendDataOwnership.test.ts`, `docs/FRONTEND.md`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `docs/FRONTEND.md` for frontend data ownership architecture semantics.
- **Failing test first**: `tests/architecture/frontendDataOwnership.test.ts::frontend data ownership` — asserts data ownership docs are harness-bound and route/UI source cannot directly own server-state primitives under the `web/` test command.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Route modules under `web/src/routes` and presentational UI under `web/src/features/*/ui` must not directly reference `useQuery`, `useMutation`, `useInfiniteQuery`, `getApi`, `postApi`, or `queryClient.set*`; feature API hooks, page hooks, and controllers remain the owning boundary.
- **On-demand context**: Frontend explorer report, `docs/FRONTEND.md`, feature-owned API hooks/controllers, and current frontend architecture tests.
- **Kill/defer criteria**: Stop if the gate scans feature-owned API hooks, weakens the documented forbidden primitive list, or requires browser/e2e execution.
- **Eval/repair signal**: frontend data-ownership architecture failure, stale docs binding, direct route/UI server-state reference, and review defects around feature ownership.
- **Implementation**: Add a static frontend architecture test that binds the docs to `frontendDataOwnership.test.ts` and rejects direct server-state primitive usage from route modules or presentational UI.
- **Verification**: `cd web && npm run test -- tests/architecture/frontendDataOwnership.test.ts`
- **Review owner**: parent
- **Status**: [x]

### Task 53 — Agent router frontend guardrail source-alignment gate

- **File(s)**: `AGENTS.md`, `CLAUDE.md`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 52
- **Touch set**: `AGENTS.md`, `CLAUDE.md`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `AGENTS.md` for root router shared-block semantics; coordinate with `CLAUDE.md` for root router shared-block semantics.
- **Failing test first**: `tests/architecture/test_agent_playbook_contracts.py::test_agent_router_frontend_guardrails_match_css_harness` — asserts root agent router frontend guardrails include retired CSS buckets declared by the frontend CSS harness.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Docs/contracts
- **Deterministic constraints**: AGENTS and CLAUDE shared router blocks must remain identical and must include every retired CSS bucket from `retiredGlobalCssBuckets` in `web/tests/architecture/cssArchitectureHarness.test.ts`.
- **On-demand context**: `AGENTS.md`, `CLAUDE.md`, `docs/FRONTEND.md`, `web/tests/architecture/cssArchitectureHarness.test.ts`, and `tests/architecture/test_agent_playbook_contracts.py`.
- **Kill/defer criteria**: Stop if the test hard-codes bucket names, weakens shared-router parity, or expands root routers with substantive rules that belong in `docs/`.
- **Eval/repair signal**: stale root router CSS guardrail, shared-router mismatch, and review defects around AGENTS/CLAUDE drift.
- **Implementation**: Add a source-derived architecture test for root router frontend guardrails and update both mirrored router blocks to current CSS harness retired buckets.
- **Verification**: `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_agent_router_frontend_guardrails_match_css_harness -q`
- **Review owner**: parent
- **Status**: [x]

### Task 54 — Frontend verification skill data-ownership gate

- **File(s)**: `.agents/skills/parallax-frontend-verification/SKILL.md`, `web/tests/architecture/frontendDocContract.test.ts`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 53
- **Touch set**: `.agents/skills/parallax-frontend-verification/SKILL.md`, `web/tests/architecture/frontendDocContract.test.ts`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `docs/FRONTEND.md` for frontend verification skill semantics.
- **Failing test first**: `tests/architecture/frontendDocContract.test.ts::frontend documentation contract` — asserts the frontend verification skill names the data-ownership harness and forbidden route/UI server-state primitives under the `web/` test command.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Docs/contracts
- **Deterministic constraints**: The skill must name `frontendDataOwnership.test.ts` and the forbidden primitives checked by that harness: `useQuery`, `useMutation`, `useInfiniteQuery`, `getApi`, `postApi`, and `queryClient.set`.
- **On-demand context**: `docs/FRONTEND.md`, `.agents/skills/parallax-frontend-verification/SKILL.md`, `web/tests/architecture/frontendDocContract.test.ts`, and `web/tests/architecture/frontendDataOwnership.test.ts`.
- **Kill/defer criteria**: Stop if the check hard-codes stale prose instead of binding to the data-ownership harness, or if the skill becomes a duplicate of `docs/FRONTEND.md` rather than a short verification router.
- **Eval/repair signal**: stale frontend verification skill, missing data-ownership primitive, frontend doc-contract failure, and review defects around route/UI server-state ownership.
- **Implementation**: Extend the frontend doc-contract architecture test and update the repo-scoped frontend verification skill to carry the current data-ownership gate.
- **Verification**: `cd web && npm run test -- tests/architecture/frontendDocContract.test.ts`
- **Review owner**: parent
- **Status**: [x]

### Task 55 — Architecture doc test-reference gate

- **File(s)**: `docs/ARCHITECTURE.md`, `tests/architecture/test_harness_structure.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 54
- **Touch set**: `docs/ARCHITECTURE.md`, `tests/architecture/test_harness_structure.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `docs/ARCHITECTURE.md` for architecture enforcement-test references.
- **Failing test first**: `tests/architecture/test_harness_structure.py::test_architecture_doc_test_references_are_path_qualified_and_existing` — asserts `docs/ARCHITECTURE.md` cannot use bare or missing architecture-test references.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Docs/contracts
- **Deterministic constraints**: Architecture enforcement references in `docs/ARCHITECTURE.md` must be path-qualified `tests/architecture/...py::test_*` references whose file and function exist.
- **On-demand context**: `docs/ARCHITECTURE.md`, `tests/architecture/test_harness_structure.py`, and current architecture test files.
- **Kill/defer criteria**: Stop if the parser treats ordinary code identifiers as test references or if docs keep bare `test_*` names.
- **Eval/repair signal**: bare architecture test reference, missing test file/function, stale enforcement-doc reference, and review defects around docs-as-router reliability.
- **Implementation**: Add a source-bound architecture-doc test-reference gate and replace the bare legacy-asset repository test reference with a full architecture test path.
- **Verification**: `uv run pytest tests/architecture/test_harness_structure.py::test_architecture_doc_test_references_are_path_qualified_and_existing -q`
- **Review owner**: parent
- **Status**: [x]

### Task 56 — Architecture module map source-completeness gate

- **File(s)**: `docs/ARCHITECTURE.md`, `tests/architecture/test_harness_structure.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 55
- **Touch set**: `docs/ARCHITECTURE.md`, `tests/architecture/test_harness_structure.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `docs/ARCHITECTURE.md` for architecture module-map links.
- **Failing test first**: `tests/architecture/test_harness_structure.py::test_architecture_module_map_links_every_domain_architecture_doc` — asserts the global architecture module map markdown-links every current domain `ARCHITECTURE.md` file.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Docs/contracts
- **Deterministic constraints**: The module map in `docs/ARCHITECTURE.md` must have markdown links for exactly the current `src/parallax/domains/*/ARCHITECTURE.md` files; bare code paths and stale links do not satisfy the gate.
- **On-demand context**: `docs/ARCHITECTURE.md`, `tests/architecture/test_harness_structure.py`, and `src/parallax/domains/*/ARCHITECTURE.md`.
- **Kill/defer criteria**: Stop if the test accepts bare backticked paths, ignores removed domain docs, or expands into checking prose wording instead of source/link completeness.
- **Eval/repair signal**: missing domain architecture link, stale domain architecture link, non-clickable module map entry, and review defects around source-backed architecture navigation.
- **Implementation**: Add a source-derived module-map architecture test and convert the Narrative architecture row to the same markdown-link shape as the other domain rows.
- **Verification**: `uv run pytest tests/architecture/test_harness_structure.py::test_architecture_module_map_links_every_domain_architecture_doc -q`
- **Review owner**: parent
- **Status**: [x]

### Task 57 — Architecture test taxonomy exact-inventory gate

- **File(s)**: `docs/TESTING.md`, `tests/architecture/test_test_lane_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 56
- **Touch set**: `docs/TESTING.md`, `tests/architecture/test_test_lane_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `docs/TESTING.md` for architecture test taxonomy inventory.
- **Failing test first**: `tests/architecture/test_test_lane_contracts.py::test_architecture_tests_declare_harness_taxonomy` — asserts `docs/TESTING.md` architecture-test taxonomy rows exactly match current `tests/architecture/test_*.py` files.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Docs/contracts
- **Deterministic constraints**: The architecture taxonomy table in `docs/TESTING.md` must list exactly the current `tests/architecture/test_*.py` files; missing and stale rows both fail.
- **On-demand context**: `docs/TESTING.md`, `tests/architecture/test_test_lane_contracts.py`, and current files under `tests/architecture`.
- **Kill/defer criteria**: Stop if the gate only checks presence and still allows stale rows, or if the taxonomy row duplicates implementation details instead of class/review note.
- **Eval/repair signal**: missing taxonomy row, stale taxonomy row, harness taxonomy failure, and review defects around test-lane documentation.
- **Implementation**: Strengthen the taxonomy architecture test to compare exact file sets and add the missing public-contracts doc-alignment row to `docs/TESTING.md`.
- **Verification**: `uv run pytest tests/architecture/test_test_lane_contracts.py::test_architecture_tests_declare_harness_taxonomy -q`
- **Review owner**: parent
- **Status**: [x]

### Task 58 — Tech debt reference source/test gate

- **File(s)**: `docs/TECH_DEBT.md`, `tests/architecture/test_harness_structure.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 57
- **Touch set**: `docs/TECH_DEBT.md`, `tests/architecture/test_harness_structure.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `docs/TECH_DEBT.md` for active debt reference hygiene.
- **Failing test first**: `tests/architecture/test_harness_structure.py::test_open_tech_debt_references_current_source_and_test_paths` — asserts open `docs/TECH_DEBT.md` source/test/doc references use self-contained repo-root paths and point at current files and test functions.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Docs/contracts
- **Deterministic constraints**: The gate must check only open debt rows, require source/test/doc references to start with `src/`, `tests/`, `web/`, `scripts/`, or `docs/`, resolve `path:line` and `file.py::Class::test_name` references, reject bare `::test_*` shorthand, and must not preserve deleted integration files as compatibility breadcrumbs.
- **On-demand context**: `docs/TECH_DEBT.md`, `tests/architecture/test_harness_structure.py`, current files under `tests/integration`, and current evidence repository insert shape.
- **Kill/defer criteria**: Stop if the gate expands into archived/generated/reference docs, if it reports intentionally retired-path examples outside open debt, or if fixing requires recreating deleted tests.
- **Eval/repair signal**: missing source/test file, missing test function, stale open debt table row, and review defects around active technical-debt truthfulness.
- **Implementation**: Add the open-tech-debt reference architecture test, update stale and unrooted paths, remove open rows for deleted historical integration files, reject bare `::test_*` shorthand, and rename remaining test references to current functions.
- **Verification**: `uv run pytest tests/architecture/test_harness_structure.py::test_open_tech_debt_references_current_source_and_test_paths -q`
- **Review owner**: parent
- **Status**: [x]

### Task 59 — Governance rule overfit split

- **File(s)**: `docs/TECH_DEBT.md`, `tests/architecture/test_harness_structure.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 58
- **Touch set**: `docs/TECH_DEBT.md`, `tests/architecture/test_harness_structure.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `tests/architecture/test_harness_structure.py` for governance rule harness edits.
- **Failing test first**: `tests/architecture/test_harness_structure.py::test_rule_ownership tests/architecture/test_harness_structure.py::test_routers_have_no_governance_phrases` — asserts governance rules have exactly one owning doc and do not leak into root router prose.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Replace the mixed `test_rule_uniqueness` gate with separate ownership and router-leak tests; use named multi-anchor rule contracts instead of single verbatim phrase keys; remove the resolved open TECH_DEBT rows.
- **On-demand context**: `tests/architecture/test_harness_structure.py`, `docs/TECH_DEBT.md`, root governance docs under `docs/`, `AGENTS.md`, and `CLAUDE.md`.
- **Kill/defer criteria**: Stop if the new anchors match multiple owners, if router checks only look for one incidental word, or if resolved debt remains open.
- **Eval/repair signal**: governance ownership failure, router leak failure, brittle phrase-only test review defect, and stale open TECH_DEBT row.
- **Implementation**: Replace `RULE_PHRASES` with `GOVERNANCE_RULE_ANCHORS`, add `_governance_paths` and `_has_rule_anchors`, split the test into `test_rule_ownership` plus `test_routers_have_no_governance_phrases`, and delete the resolved TECH_DEBT rows.
- **Verification**: `uv run pytest tests/architecture/test_harness_structure.py::test_rule_ownership tests/architecture/test_harness_structure.py::test_routers_have_no_governance_phrases -q`
- **Review owner**: parent
- **Status**: [x]

### Task 60 — Evidence entity type shim hard cut

- **File(s)**: `src/parallax/domains/evidence/types/entity.py`, `src/parallax/domains/evidence/services/entity_extractor.py`, `src/parallax/domains/evidence/interfaces.py`, `src/parallax/app/surfaces/api/ws.py`, `tests/unit/test_entity_extractor.py`, `tests/architecture/test_src_domain_architecture.py`, `docs/TECH_DEBT.md`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 59
- **Touch set**: `src/parallax/domains/evidence/types/entity.py`, `src/parallax/domains/evidence/services/entity_extractor.py`, `src/parallax/domains/evidence/interfaces.py`, `src/parallax/app/surfaces/api/ws.py`, `tests/unit/test_entity_extractor.py`, `tests/architecture/test_src_domain_architecture.py`, `docs/TECH_DEBT.md`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/domains/evidence/services/entity_extractor.py` for entity normalization import ownership.
- **Failing test first**: `tests/architecture/test_src_domain_architecture.py::test_domain_types_do_not_import_upward_layers` — asserts domain `types/` modules cannot import services, repositories, queries, read models, or runtime modules.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Domain implementation
- **Deterministic constraints**: Remove the thin re-export shim; `ExtractedEntity`, `EVM_QUERY_CHAINS`, address normalization, and TON address validation must live in `domains/evidence/types/entity.py`; upper layers import from types or interfaces, not from the old service re-export.
- **On-demand context**: `src/parallax/domains/evidence/types/entity.py`, `src/parallax/domains/evidence/services/entity_extractor.py`, `src/parallax/domains/evidence/repositories`, `src/parallax/app/surfaces/api/ws.py`, and entity extractor unit tests.
- **Kill/defer criteria**: Stop if the fix keeps `types/entity.py` importing from services, adds an allowlist for this shim, or changes entity extraction behavior without focused unit evidence.
- **Eval/repair signal**: upward type import violation, entity extraction regression, address normalization regression, and stale TECH_DEBT shim row.
- **Implementation**: Move entity value objects and normalization primitives into the types module, make the extractor consume types, route API WebSocket normalization through the evidence interface, update unit imports, add the architecture gate, and remove the resolved TECH_DEBT row.
- **Verification**: `uv run pytest tests/architecture/test_src_domain_architecture.py::test_domain_types_do_not_import_upward_layers -q`
- **Review owner**: parent
- **Status**: [x]

### Task 61 — Domain interface runtime import hard cut

- **File(s)**: `src/parallax/domains/token_intel/interfaces.py`, `src/parallax/domains/token_intel/services/token_resolution_refresh.py`, `src/parallax/domains/token_intel/runtime/token_intent_rebuild.py`, `src/parallax/app/surfaces/cli/commands/ops.py`, `tests/unit/test_token_resolution_refresh.py`, `tests/architecture/test_src_domain_architecture.py`, `docs/TECH_DEBT.md`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 60
- **Touch set**: `src/parallax/domains/token_intel/interfaces.py`, `src/parallax/domains/token_intel/services/token_resolution_refresh.py`, `src/parallax/domains/token_intel/runtime/token_intent_rebuild.py`, `src/parallax/app/surfaces/cli/commands/ops.py`, `tests/unit/test_token_resolution_refresh.py`, `tests/architecture/test_src_domain_architecture.py`, `docs/TECH_DEBT.md`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Removed file(s)**: `src/parallax/domains/token_intel/runtime/token_resolution_refresh.py`
- **Conflict set**: coordinate with `src/parallax/domains/token_intel/interfaces.py` for domain interface export ownership.
- **Failing test first**: `tests/architecture/test_src_domain_architecture.py::test_domain_interfaces_do_not_import_runtime_modules` — asserts domain interface modules cannot import runtime modules.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Domain implementation
- **Deterministic constraints**: `token_intel/interfaces.py` must not import runtime modules; the token resolution refresh use case must live under services; the old runtime module must be deleted rather than kept as a forwarding compatibility file.
- **On-demand context**: `src/parallax/domains/token_intel/interfaces.py`, token resolution refresh unit tests, resolution refresh worker imports, CLI ops imports, and cross-domain import architecture rules.
- **Kill/defer criteria**: Stop if the fix introduces a cross-domain direct import from `asset_market` into `token_intel` internals, leaves `runtime/token_resolution_refresh.py` as a shim, or adds an allowlist for the interface runtime import.
- **Eval/repair signal**: domain interface runtime import failure, token resolution refresh unit regression, cross-domain import regression, and stale TECH_DEBT runtime-coupling row.
- **Implementation**: Move token resolution refresh functions to `services/token_resolution_refresh.py`, delete the old runtime module, point same-domain runtime/CLI/tests at the new service owner, keep cross-domain worker imports through `token_intel.interfaces`, add the architecture gate, and remove the resolved TECH_DEBT row.
- **Verification**: `uv run pytest tests/architecture/test_src_domain_architecture.py::test_domain_interfaces_do_not_import_runtime_modules -q`
- **Review owner**: parent
- **Status**: [x]

### Task 62 — Tech debt duplicate-symbol claim gate

- **File(s)**: `docs/TECH_DEBT.md`, `tests/architecture/test_harness_structure.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 61
- **Touch set**: `docs/TECH_DEBT.md`, `tests/architecture/test_harness_structure.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `docs/TECH_DEBT.md` for active debt row semantics.
- **Failing test first**: `tests/architecture/test_harness_structure.py::test_open_tech_debt_duplicate_symbol_claims_match_current_sources` — asserts duplicate-symbol debt claims match cited source contents.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Docs/contracts
- **Deterministic constraints**: Open TECH_DEBT duplicate-symbol claims must cite current source facts; resolved duplicate-constant rows must be removed rather than left as compatibility breadcrumbs; the harness must validate a reusable claim pattern rather than a single constant name.
- **On-demand context**: `docs/TECH_DEBT.md`, existing TECH_DEBT path-reference architecture tests, `src/parallax/domains/token_intel/_constants.py`, and `src/parallax/domains/asset_market/repositories/registry_repository.py`.
- **Kill/defer criteria**: Stop if the fix hard-codes only `TOKEN_RADAR_RESOLVER_POLICY_VERSION`, deletes unrelated debt rows, or weakens existing TECH_DEBT path-reference checks.
- **Eval/repair signal**: stale duplicate-symbol TECH_DEBT claim, missing source-backed evidence for active debt, and SDD validator evidence drift.
- **Implementation**: Add a TECH_DEBT duplicate-symbol claim architecture gate, remove the stale resolver-policy duplicate row after RED, update SDD records, and regenerate the SDD work index.
- **Verification**: `uv run pytest tests/architecture/test_harness_structure.py::test_open_tech_debt_duplicate_symbol_claims_match_current_sources -q`
- **Review owner**: parent
- **Status**: [x]

### Task 63 — Generated WebSocket protocol type-literal gate

- **File(s)**: `scripts/regen_ws_protocol.py`, `docs/generated/ws-protocol.md`, `docs/generated/README.md`, `docs/TECH_DEBT.md`, `tests/architecture/test_harness_structure.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 62
- **Touch set**: `scripts/regen_ws_protocol.py`, `docs/generated/ws-protocol.md`, `docs/generated/README.md`, `docs/TECH_DEBT.md`, `tests/architecture/test_harness_structure.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `docs/generated/README.md` for generated-doc source-map semantics.
- **Failing test first**: `tests/architecture/test_harness_structure.py::test_generated_ws_protocol_documents_current_type_literals` — asserts generated WebSocket protocol docs include current source `type` literals.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Docs/contracts
- **Deterministic constraints**: Generated WebSocket docs must be source-derived; current JSON `type` literals must be listed even before typed payload classes exist; generated README wording and TECH_DEBT wording must describe the current generator behavior rather than the old class-only output.
- **On-demand context**: `src/parallax/app/surfaces/api/ws.py`, `scripts/regen_ws_protocol.py`, `docs/generated/ws-protocol.md`, `docs/generated/README.md`, and the existing generated-doc source-map harness.
- **Kill/defer criteria**: Stop if the generator hand-maintains message types, removes the class table without replacing source-derived coverage, weakens generated README path checks, or edits unrelated generated docs that require Postgres regeneration.
- **Eval/repair signal**: missing WebSocket type literal in generated docs, stale generated README source-map description, stale TECH_DEBT row about sparse class-only output, and SDD generated index drift.
- **Implementation**: Add an AST-based type-literal architecture gate, teach `scripts/regen_ws_protocol.py` to emit type-literal and source-class sections, regenerate `docs/generated/ws-protocol.md`, update generated README and TECH_DEBT wording, then regenerate the SDD work index.
- **Verification**: `uv run pytest tests/architecture/test_harness_structure.py::test_generated_ws_protocol_documents_current_type_literals -q`
- **Review owner**: parent
- **Status**: [x]

### Task 64 — Generated WebSocket protocol freshness gate

- **File(s)**: `Makefile`, `scripts/regen_ws_protocol.py`, `tests/architecture/test_harness_structure.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 63
- **Touch set**: `Makefile`, `scripts/regen_ws_protocol.py`, `tests/architecture/test_harness_structure.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `Makefile` for check-all generated-doc gates.
- **Failing test first**: `tests/architecture/test_harness_structure.py::test_make_check_all_checks_ws_protocol_snapshot` — asserts `check-all` runs the WebSocket protocol freshness check.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `scripts/regen_ws_protocol.py --check` must be non-mutating and exit non-zero on stale output; `make check-all` must run the check before integration, e2e, golden, or coverage gates; the implementation must not require Postgres or generated DB docs.
- **On-demand context**: `Makefile` `check-all`, `scripts/regen_ws_protocol.py`, `docs/generated/ws-protocol.md`, and generated-doc architecture tests.
- **Kill/defer criteria**: Stop if the fix only updates docs without executable `--check`, runs full `make docs-generated` inside `check-all`, or introduces a database-backed generated-doc dependency before integration gates.
- **Eval/repair signal**: stale WebSocket protocol snapshot, missing `check-all` generated-doc gate, and SDD generated index drift.
- **Implementation**: Add `--check` mode to the WebSocket protocol generator, wire `make check-all` to run it before `make check`, and add an architecture test for the Makefile gate.
- **Verification**: `uv run pytest tests/architecture/test_harness_structure.py::test_make_check_all_checks_ws_protocol_snapshot -q`
- **Review owner**: parent
- **Status**: [x]

### Task 65 — Generated score-version freshness gate

- **File(s)**: `Makefile`, `scripts/regen_score_versions.py`, `tests/architecture/test_harness_structure.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 64
- **Touch set**: `Makefile`, `scripts/regen_score_versions.py`, `tests/architecture/test_harness_structure.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `Makefile` for check-all generated-doc gates.
- **Failing test first**: `tests/architecture/test_harness_structure.py::test_make_check_all_checks_score_versions_snapshot` — asserts `check-all` runs the score-version freshness check.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `scripts/regen_score_versions.py --check` must be non-mutating and exit non-zero on stale output; `make check-all` must run the check before integration, e2e, golden, or coverage gates; the implementation must not require Postgres or generated DB docs.
- **On-demand context**: `Makefile` `check-all`, `scripts/regen_score_versions.py`, `docs/generated/score-versions.md`, and generated-doc architecture tests.
- **Kill/defer criteria**: Stop if the fix only updates docs without executable `--check`, runs full `make docs-generated` inside `check-all`, or introduces a database-backed generated-doc dependency before integration gates.
- **Eval/repair signal**: stale score-version snapshot, missing `check-all` generated-doc gate, and SDD generated index drift.
- **Implementation**: Add `--check` mode to the score-version generator, wire `make check-all` to run it before `make check`, and add an architecture test for the Makefile gate.
- **Verification**: `uv run pytest tests/architecture/test_harness_structure.py::test_make_check_all_checks_score_versions_snapshot -q`
- **Review owner**: parent
- **Status**: [x]

### Task 66 — Source-derived generated-doc freshness gate

- **File(s)**: `Makefile`, `scripts/regen_pulse_agent_desk_decisions.py`, `tests/architecture/test_harness_structure.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 65
- **Touch set**: `Makefile`, `scripts/regen_pulse_agent_desk_decisions.py`, `tests/architecture/test_harness_structure.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `Makefile` for check-all generated-doc gates.
- **Failing test first**: `tests/architecture/test_harness_structure.py::test_make_check_all_checks_non_db_generated_snapshots` — derives generator scripts from `docs/generated/README.md` and requires every non-DB generator to run with `--check` inside `check-all`.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `scripts/regen_pulse_agent_desk_decisions.py --check` must be non-mutating and exit non-zero on stale output; the architecture test must derive expected scripts from `docs/generated/README.md`; `make check-all` must run the generated-doc freshness checks before integration, e2e, golden, or coverage gates; the DB schema generator remains excluded because it requires Postgres.
- **On-demand context**: `docs/generated/README.md`, `Makefile` `check-all`, `scripts/regen_pulse_agent_desk_decisions.py`, and generated-doc architecture tests.
- **Kill/defer criteria**: Stop if the fix adds only another hand-coded assertion without source-map coverage, runs Postgres-backed DB regeneration before integration gates, or mutates generated docs in `--check` mode.
- **Eval/repair signal**: generated README names a non-DB generator that lacks `--check` coverage in `check-all`, stale Pulse Agent Desk decisions snapshot, and SDD generated index drift.
- **Implementation**: Replace the one-off generated-doc gate pattern with a README-derived architecture test for non-DB generators, add `--check` mode to the Pulse Agent Desk decisions generator, wire `make check-all` to run it before `make check`, then regenerate the SDD work index.
- **Verification**: `uv run pytest tests/architecture/test_harness_structure.py::test_make_check_all_checks_non_db_generated_snapshots -q`
- **Review owner**: parent
- **Status**: [x]

### Task 67 — Task-bound subagent required-reading evidence gate

- **File(s)**: `scripts/subagent_report_contract.py`, `docs/agent-playbook/subagent-handoff-template.md`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 66
- **Touch set**: `scripts/subagent_report_contract.py`, `docs/agent-playbook/subagent-handoff-template.md`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with docs/agent-playbook for subagent report semantics.
- **Failing test first**: `tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_requires_task_classification_and_required_reading_evidence`, `tests/architecture/test_agent_playbook_contracts.py::test_subagent_handoff_templates_define_context_and_conflict_contracts` — assert task-bound reports cannot pass without reading evidence and the handoff template names the required report section.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Task-bound subagent reports must include `## Required Reading Evidence` with `Task classification:`, `AGENTS.md`, `docs/agent-playbook/task-reading-matrix.md`, and task on-demand context paths; unbound read-only reports remain lightweight; the validator must not trust prose-only handoff claims.
- **On-demand context**: `docs/agent-playbook/task-reading-matrix.md`, `docs/agent-playbook/subagent-handoff-template.md`, `scripts/subagent_report_contract.py`, and `scripts/validate_subagent_report.py`.
- **Kill/defer criteria**: Stop if the fix only updates templates without executable report validation, makes every unbound exploratory report require task metadata, or duplicates the task reading matrix inside the validator.
- **Eval/repair signal**: subagent report accepted without task classification, missing required-reading evidence, stale handoff template, and SDD generated index drift.
- **Implementation**: Add a task-bound required-reading evidence check to `scripts/subagent_report_contract.py`, update the handoff template report contract, and cover both validator and template behavior with architecture tests.
- **Verification**: `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_requires_task_classification_and_required_reading_evidence tests/architecture/test_agent_playbook_contracts.py::test_subagent_handoff_templates_define_context_and_conflict_contracts -q`
- **Review owner**: parent
- **Status**: [x]

### Task 68 — Spec background cited-line relevance gate

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 67
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with docs/sdd/features/active/2026-06-09-executable-harness-hard-cut for SDD background/source citations.
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_spec_background_rejects_stale_local_citation_lines` — asserts a local Background citation cannot pass when the cited line exists but omits the backticked evidence token claimed by the Background block.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Local Background citations remain path/line based; when a claim block contains backticked evidence tokens that are not citations, at least one cited local line must mention each token; external HTTPS citation blocks remain accepted; current active specs must cite current lines.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/WORKFLOW.md`, and `scripts/regen_sdd_work_index.py`.
- **Kill/defer criteria**: Stop if the fix attempts broad natural-language citation scoring, requires network access for external citations, or weakens the existing path/line existence check.
- **Eval/repair signal**: stale Background line citation, `spec-background-uncited`, active spec citation drift, and SDD generated index drift.
- **Implementation**: Add cited-line evidence-token validation for local Background citations and update the active hard-cut spec Background to cite current workflow and generated-index lines.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_spec_background_rejects_stale_local_citation_lines -q`
- **Review owner**: parent
- **Status**: [x]

### Task 69 — Worker runtime constraint classification manifest ownership

- **File(s)**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_runtime_worker_constraint_hard_cut.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 68
- **Touch set**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_runtime_worker_constraint_hard_cut.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/worker_manifest.py` for worker inventory semantics.
- **Failing test first**: `tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_every_registered_worker_has_runtime_constraint_classification` — asserts each registered worker declares its runtime constraint on `WorkerManifest`.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `WorkerManifest` must declare `runtime_constraint` for every registered worker; architecture tests must not maintain a separate worker-to-classification inventory; allowed runtime constraint values are represented by the `WorkerRuntimeConstraint` enum.
- **On-demand context**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_runtime_worker_constraint_hard_cut.py`, and worker manifest architecture tests.
- **Kill/defer criteria**: Stop if the fix leaves a duplicate test-side worker classification map, introduces compatibility aliases for old classifications, or infers classifications from worker names instead of source-owned manifest data.
- **Eval/repair signal**: worker classification drift, duplicate worker inventory, stale architecture test map, and SDD generated index drift.
- **Implementation**: Add `WorkerRuntimeConstraint` to the worker manifest, populate every manifest entry, remove the test-owned `WORKER_CLASSIFICATION` map, and assert each manifest carries a valid enum value.
- **Verification**: `uv run pytest tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_every_registered_worker_has_runtime_constraint_classification -q`
- **Review owner**: parent
- **Status**: [x]

### Task 70 — Worker Inventory architecture tests use source manifests

- **File(s)**: `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 69
- **Touch set**: `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `tests/architecture/test_worker_runtime_contracts.py` for worker runtime test constants.
- **Failing test first**: `tests/architecture/test_worker_inventory_contract.py::test_architecture_tests_do_not_import_peer_architecture_tests_as_sources` — asserts architecture tests cannot import peer architecture tests as source registries.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Worker Inventory architecture tests must derive worker keys, worker classes, and read-model writer rows from `WorkerManifest`; architecture tests must not import other architecture tests as hidden source registries; no compatibility alias for the old peer-test constants is allowed.
- **On-demand context**: `tests/architecture/test_worker_inventory_contract.py`, `tests/architecture/test_worker_runtime_contracts.py`, `src/parallax/app/runtime/worker_manifest.py`, and `docs/WORKERS.md`.
- **Kill/defer criteria**: Stop if the fix keeps a peer architecture-test import, moves the duplicated registry to another test file, or weakens Worker Inventory doc/source comparison.
- **Eval/repair signal**: peer architecture-test imports, Worker Inventory doc drift, duplicate read-model writer rows in `WorkerManifest`, and SDD generated index drift.
- **Implementation**: Add a peer-test import ban, replace `MANIFEST_WORKER_CLASSES` / `SINGLE_WRITER_READ_MODELS` imports with source-derived `WorkerManifest` data, and remove dead test-side read-model derivation helpers.
- **Verification**: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_architecture_tests_do_not_import_peer_architecture_tests_as_sources -q`
- **Review owner**: parent
- **Status**: [x]

### Task 71 — WorkerManifest owns table ownership composition

- **File(s)**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 70
- **Touch set**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/worker_manifest.py` for worker ownership semantics.
- **Failing test first**: `tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_exposes_owned_tables_as_source_contract` — asserts each manifest exposes the deduped owned-table contract and queue-health tables remain inside it.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `WorkerManifest.owned_tables` must be the canonical deduped composition of input-observation, fact, read-model, control-plane, and side-effect-ledger writes; manifest validation must consume this contract; no compatibility alias for duplicated ownership tuple assembly is allowed.
- **On-demand context**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, and worker ownership architecture tests.
- **Kill/defer criteria**: Stop if the fix keeps multiple ownership tuple assembly formulas, changes manifest ownership semantics without tests, or touches dirty worker runtime contract files.
- **Eval/repair signal**: ownership tuple drift, queue-health table outside owned tables, Worker Inventory doc drift, and SDD generated index drift.
- **Implementation**: Add `WorkerManifest.owned_tables`, use it in manifest queue-health ownership validation, and add an architecture test for the source-owned table ownership contract.
- **Verification**: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_exposes_owned_tables_as_source_contract -q`
- **Review owner**: parent
- **Status**: [x]

### Task 72 — WorkerManifest owns read-model writer mapping

- **File(s)**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 71
- **Touch set**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/worker_manifest.py` for read-model writer ownership semantics.
- **Failing test first**: `tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_exposes_read_model_writer_mapping` — asserts `worker_manifest.py` exposes the unique read-model writer map.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `read_model_writer_by_table()` must be source-derived from `WorkerManifest.writes_read_models`, must reject duplicate read-model writers, and Worker Inventory docs checks must consume it instead of rebuilding a writer registry locally.
- **On-demand context**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, and read-model writer ownership checks.
- **Kill/defer criteria**: Stop if the fix keeps a test-side writer registry, silently accepts duplicate read-model writers, or touches dirty worker runtime contract files.
- **Eval/repair signal**: duplicate read-model writer, Worker Inventory doc drift, local writer-registry reconstruction, and SDD generated index drift.
- **Implementation**: Add `read_model_writer_by_table()` to the worker manifest module, export it, and refactor the Worker Inventory docs check to use it.
- **Verification**: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_exposes_read_model_writer_mapping -q`
- **Review owner**: parent
- **Status**: [x]

### Task 73 — WorkerManifest validates read-model writer uniqueness

- **File(s)**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 72
- **Touch set**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/worker_manifest.py` for read-model writer ownership semantics.
- **Failing test first**: `tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_read_model_writers` — patches duplicate read-model writers and asserts manifest validation rejects them.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `_validate_worker_manifests()` must call the source-owned read-model writer map so duplicate read-model writers fail before downstream docs or architecture harnesses consume the manifest.
- **On-demand context**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, and read-model writer ownership checks.
- **Kill/defer criteria**: Stop if duplicate read-model writers are only caught by docs comparisons, if validation accepts patched duplicates, or if the fix touches dirty worker runtime contract files.
- **Eval/repair signal**: duplicate read-model writer, manifest import-time validation drift, Worker Inventory doc drift, and SDD generated index drift.
- **Implementation**: Reuse `read_model_writer_by_table()` inside `_validate_worker_manifests()` and add a monkeypatch-based architecture test proving duplicate read-model writers raise `ValueError`.
- **Verification**: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_read_model_writers -q`
- **Review owner**: parent
- **Status**: [x]

### Task 74 — WorkerManifest validates read-model identity ownership

- **File(s)**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 73
- **Touch set**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/worker_manifest.py` for read-model identity semantics.
- **Failing test first**: `tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_unowned_read_model_identities` — patches an unowned `current_read_model_identities` entry and asserts manifest validation rejects it.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `current_read_model_identities` entries must be a subset of the same worker's `writes_read_models`; manifest validation must reject unowned identity rows before downstream docs or architecture harnesses consume the manifest.
- **On-demand context**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, and stable read-model identity ownership checks.
- **Kill/defer criteria**: Stop if unowned identity rows are tolerated as stale breadcrumbs, if validation only checks missing identities one way, or if the fix touches dirty worker runtime contract files.
- **Eval/repair signal**: unowned stable read-model identity, stale identity breadcrumb, manifest import-time validation drift, and SDD generated index drift.
- **Implementation**: Add reverse ownership validation for `current_read_model_identities` and cover it with a monkeypatch-based architecture test.
- **Verification**: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_unowned_read_model_identities -q`
- **Review owner**: parent
- **Status**: [x]

### Task 75 — WorkerManifest validates unique read-model identity entries

- **File(s)**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 74
- **Touch set**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/worker_manifest.py` for read-model identity semantics.
- **Failing test first**: `tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_read_model_identity_entries` — patches duplicate `current_read_model_identities` entries for one table and asserts manifest validation rejects them.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `current_read_model_identities` entries must be unique by table within one worker manifest; manifest validation must reject duplicate identity rows before downstream docs or architecture harnesses consume the manifest.
- **On-demand context**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, and stable read-model identity ownership checks.
- **Kill/defer criteria**: Stop if duplicate identity rows are tolerated as alternate current keys, if validation only checks ownership without uniqueness, or if the fix touches dirty worker runtime contract files.
- **Eval/repair signal**: duplicate stable read-model identity, ambiguous current identity contract, manifest import-time validation drift, and SDD generated index drift.
- **Implementation**: Add duplicate-table validation for `current_read_model_identities` and cover it with a monkeypatch-based architecture test.
- **Verification**: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_read_model_identity_entries -q`
- **Review owner**: parent
- **Status**: [x]

### Task 76 — WorkerManifest validates unique table declarations

- **File(s)**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 75
- **Touch set**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/worker_manifest.py` for table-declaration validation semantics.
- **Failing test first**: `tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_table_declarations` — patches a duplicate `writes_control_plane` table entry and asserts manifest validation rejects it.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Each `WorkerManifest` table-declaration field must be unique by table name within that field; manifest validation must reject duplicates before `owned_tables` or downstream harnesses dedupe them.
- **On-demand context**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, and source-owned worker table ownership checks.
- **Kill/defer criteria**: Stop if duplicate declarations are intentionally allowed as aliases, if validation only catches duplicates after `owned_tables` dedupe, or if the fix touches dirty worker runtime contract files.
- **Eval/repair signal**: duplicate table declaration, silent manifest dedupe, stale compatibility table breadcrumb, and SDD generated index drift.
- **Implementation**: Add per-field duplicate table validation for `WorkerManifest` table declaration tuples and cover it with a monkeypatch-based architecture test.
- **Verification**: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_table_declarations -q`
- **Review owner**: parent
- **Status**: [x]

### Task 77 — Current read-model identity columns are unique

- **File(s)**: `src/parallax/app/runtime/worker_manifest.py`, `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_inventory_contract.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 76
- **Touch set**: `src/parallax/app/runtime/worker_manifest.py`, `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_inventory_contract.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/worker_manifest.py` for stable identity validation semantics.
- **Failing test first**: `tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_read_model_identity_columns` and `tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_run_generation_identity_and_skips_unchanged` — patch or construct duplicate stable identity columns and assert validation rejects them.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Stable current read-model identity columns must be unique inside each identity tuple; both manifest import-time validation and `CurrentReadModelPublisher` construction must reject duplicate columns before downstream serving identity code can normalize them accidentally.
- **On-demand context**: `src/parallax/app/runtime/worker_manifest.py`, `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_inventory_contract.py`, and current read-model identity static contracts.
- **Kill/defer criteria**: Stop if duplicate identity columns are intentionally supported as a semantic alias, if only the publisher or only the manifest is validated, or if the fix touches dirty worker runtime contract files.
- **Eval/repair signal**: duplicate stable identity column, malformed current read-model key, manifest/publisher validation drift, and SDD generated index drift.
- **Implementation**: Add duplicate-column validation for `CurrentReadModelPublisher.identity_columns` and `WorkerManifest.current_read_model_identities`.
- **Verification**: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_read_model_identity_columns tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_run_generation_identity_and_skips_unchanged -q`
- **Review owner**: parent
- **Status**: [x]

### Task 78 — WorkerManifest validates non-empty read-model identity columns

- **File(s)**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 77
- **Touch set**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/worker_manifest.py` for stable identity validation semantics.
- **Failing test first**: `tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_empty_read_model_identity_columns` — patches a current read-model identity entry with an empty identity column tuple and asserts manifest validation rejects it.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Every `WorkerManifest.current_read_model_identities` entry must declare at least one stable identity column; manifest validation must reject empty identity column tuples before downstream harnesses treat the entry as proof of stable serving identity.
- **On-demand context**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, and current read-model identity validation checks.
- **Kill/defer criteria**: Stop if empty identity tuples are intentionally supported as a placeholder, if validation only relies on `CurrentReadModelPublisher`, or if the fix touches dirty worker runtime contract files.
- **Eval/repair signal**: empty stable identity column list, placeholder current identity declaration, manifest validation drift, and SDD generated index drift.
- **Implementation**: Add empty-column validation for `WorkerManifest.current_read_model_identities` and cover it with a monkeypatch-based architecture test.
- **Verification**: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_empty_read_model_identity_columns -q`
- **Review owner**: parent
- **Status**: [x]

### Task 79 — WorkerManifest validates non-blank table declarations

- **File(s)**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 78
- **Touch set**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/worker_manifest.py` for table-declaration validation semantics.
- **Failing test first**: `tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_table_declarations` — patches a blank `writes_control_plane` table entry and asserts manifest validation rejects it.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Worker table-declaration fields and `queue_depth_table` must not contain blank table names; manifest validation must reject blank table declarations before ownership, queue health, or docs harnesses consume the manifest.
- **On-demand context**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, and source-owned worker table declaration checks.
- **Kill/defer criteria**: Stop if blank table names are intentionally supported as placeholders, if validation only checks duplicates, or if the fix touches dirty worker runtime contract files.
- **Eval/repair signal**: blank table declaration, whitespace table name, placeholder ownership entry, manifest validation drift, and SDD generated index drift.
- **Implementation**: Add blank-table validation for `WorkerManifest` table declaration tuples and `queue_depth_table`, and reuse the table-declaration field helper in duplicate validation.
- **Verification**: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_table_declarations -q`
- **Review owner**: parent
- **Status**: [x]

### Task 80 — Current read-model identity columns are non-blank

- **File(s)**: `src/parallax/app/runtime/worker_manifest.py`, `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_inventory_contract.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 79
- **Touch set**: `src/parallax/app/runtime/worker_manifest.py`, `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_inventory_contract.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/worker_manifest.py` for stable identity validation semantics.
- **Failing test first**: `tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_read_model_identity_columns` and `tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_run_generation_identity_and_skips_unchanged` — patch or construct blank stable identity columns and assert validation rejects them.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Stable current read-model identity column names must not be blank; both manifest import-time validation and `CurrentReadModelPublisher` construction must reject blank identity columns before downstream serving identity code can treat whitespace as a key.
- **On-demand context**: `src/parallax/app/runtime/worker_manifest.py`, `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_inventory_contract.py`, and current read-model identity static contracts.
- **Kill/defer criteria**: Stop if blank identity columns are intentionally supported as placeholders, if only the publisher or only the manifest is validated, or if the fix touches dirty worker runtime contract files.
- **Eval/repair signal**: blank stable identity column, whitespace current read-model key, manifest/publisher validation drift, and SDD generated index drift.
- **Implementation**: Add blank-column validation for `CurrentReadModelPublisher.identity_columns` and `WorkerManifest.current_read_model_identities`.
- **Verification**: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_read_model_identity_columns tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_run_generation_identity_and_skips_unchanged -q`
- **Review owner**: parent
- **Status**: [x]

### Task 81 — Current read-model identity tables are non-blank

- **File(s)**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 80
- **Touch set**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/worker_manifest.py` for stable identity validation semantics.
- **Failing test first**: `tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_read_model_identity_tables` — patch a stable identity entry with a blank read-model table name and assert manifest validation raises a dedicated blank identity-table error before ownership or missing-identity checks.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Stable current read-model identity table names must not be blank; manifest validation must reject whitespace table names before ownership, missing-identity, or downstream harness checks consume the manifest.
- **On-demand context**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, and current read-model identity validation checks.
- **Kill/defer criteria**: Stop if blank identity table names are intentionally supported as placeholders, if validation only relies on later unowned/missing identity errors, or if the fix touches dirty worker runtime contract files.
- **Eval/repair signal**: blank read-model identity table, whitespace current read-model key, ownership-check masking, manifest validation drift, and SDD generated index drift.
- **Implementation**: Add blank-table validation for `WorkerManifest.current_read_model_identities` entries before duplicate, missing, and unowned identity checks.
- **Verification**: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_read_model_identity_tables -q`
- **Review owner**: parent
- **Status**: [x]

### Task 82 — Dirty-target consumers declare dirty targets

- **File(s)**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 81
- **Touch set**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/worker_manifest.py` for runtime constraint validation semantics.
- **Failing test first**: `tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_dirty_consumers_without_dirty_targets` — patch a `DIRTY_TARGET_CONSUMER` manifest to remove `dirty_target_tables` and assert manifest validation raises a dedicated dirty-target lifecycle error.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `DIRTY_TARGET_CONSUMER` manifests must declare at least one dirty target table before worker lifecycle, queue-health, or ownership harnesses can treat the runtime classification as source truth.
- **On-demand context**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, and runtime constraint classification checks.
- **Kill/defer criteria**: Stop if a dirty-target consumer can intentionally poll without a dirty target table, if validation only relies on later ownership checks, or if the fix touches dirty worker runtime contract files.
- **Eval/repair signal**: dirty-target consumer without queue table, runtime classification drift, worker lifecycle masking, manifest validation drift, and SDD generated index drift.
- **Implementation**: Add manifest validation requiring `dirty_target_tables` whenever `runtime_constraint` is `DIRTY_TARGET_CONSUMER`.
- **Verification**: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_dirty_consumers_without_dirty_targets -q`
- **Review owner**: parent
- **Status**: [x]

### Task 83 — Leased-job consumers declare queue depth tables

- **File(s)**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 82
- **Touch set**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/worker_manifest.py` for runtime constraint validation semantics.
- **Failing test first**: `tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_leased_consumers_without_queue_depth` — patch a `LEASED_JOB_CONSUMER` manifest to remove `queue_depth_table` and assert manifest validation raises a dedicated leased-job queue-depth error.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `LEASED_JOB_CONSUMER` manifests must declare a queue depth table before worker lifecycle, queue-health, or ownership harnesses can treat the runtime classification as source truth.
- **On-demand context**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, and runtime constraint classification checks.
- **Kill/defer criteria**: Stop if a leased-job consumer can intentionally run without a queue depth table, if validation only relies on later queue-health checks, or if the fix touches dirty worker runtime contract files.
- **Eval/repair signal**: leased consumer without queue table, runtime classification drift, queue-health source masking, manifest validation drift, and SDD generated index drift.
- **Implementation**: Add manifest validation requiring `queue_depth_table` whenever `runtime_constraint` is `LEASED_JOB_CONSUMER`.
- **Verification**: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_leased_consumers_without_queue_depth -q`
- **Review owner**: parent
- **Status**: [x]

### Task 84 — Bounded provider schedulers declare provider I/O

- **File(s)**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 83
- **Touch set**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/worker_manifest.py` for runtime constraint validation semantics.
- **Failing test first**: `tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_provider_schedulers_without_provider_io` — patch a `BOUNDED_PROVIDER_SCHEDULER` manifest to clear `uses_provider_io` and assert manifest validation raises a dedicated provider-boundary error.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `BOUNDED_PROVIDER_SCHEDULER` manifests must declare provider I/O before provider-boundary, worker lifecycle, or inventory harnesses can treat the runtime classification as source truth.
- **On-demand context**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, and runtime constraint classification checks.
- **Kill/defer criteria**: Stop if a bounded provider scheduler can intentionally avoid provider I/O, if validation only relies on provider-specific docs checks, or if the fix touches dirty worker runtime contract files.
- **Eval/repair signal**: provider scheduler without provider I/O, runtime classification drift, external-data boundary masking, manifest validation drift, and SDD generated index drift.
- **Implementation**: Add manifest validation requiring `uses_provider_io` whenever `runtime_constraint` is `BOUNDED_PROVIDER_SCHEDULER`.
- **Verification**: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_provider_schedulers_without_provider_io -q`
- **Review owner**: parent
- **Status**: [x]

### Task 85 — Queue depth tables are worker-owned

- **File(s)**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 84
- **Touch set**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/worker_manifest.py` for queue ownership validation semantics.
- **Failing test first**: `tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_unowned_queue_depth_tables` — patch a manifest with `queue_depth_table="unowned_queue_jobs"` and assert manifest validation raises a dedicated queue-depth ownership error.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Every declared `queue_depth_table` must belong to the same manifest's `owned_tables` before queue-health, ownership, or worker inventory harnesses can treat the queue-depth table as source truth.
- **On-demand context**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, and queue-health ownership checks.
- **Kill/defer criteria**: Stop if queue-depth tables can intentionally be owned by a separate worker, if validation only checks blank/duplicate table declarations, or if the fix touches dirty worker runtime contract files.
- **Eval/repair signal**: unowned queue-depth table, queue-health source masking, worker ownership drift, manifest validation drift, and SDD generated index drift.
- **Implementation**: Add manifest validation rejecting `queue_depth_table` values absent from `manifest.owned_tables`.
- **Verification**: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_unowned_queue_depth_tables -q`
- **Review owner**: parent
- **Status**: [x]

### Task 86 — Side-effect ledgers belong to side-effect workers

- **File(s)**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 85
- **Touch set**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/worker_manifest.py` for side-effect ledger validation semantics.
- **Failing test first**: `tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_ledgers_on_non_side_effect_workers` — patch a non-side-effect manifest to declare `side_effect_ledgers` and assert manifest validation raises a dedicated ledger-kind ownership error.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `side_effect_ledgers` may be declared only by `AGENT_SIDE_EFFECT` or `NOTIFICATION_DELIVERY` worker kinds before ownership, side-effect, or worker inventory harnesses can treat ledger tables as source truth.
- **On-demand context**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, and side-effect ledger validation checks.
- **Kill/defer criteria**: Stop if non-side-effect workers intentionally own side-effect ledgers, if validation only checks side-effect workers for missing ledgers, or if the fix touches dirty worker runtime contract files.
- **Eval/repair signal**: non-side-effect ledger ownership, stale ledger breadcrumb, side-effect boundary drift, manifest validation drift, and SDD generated index drift.
- **Implementation**: Add manifest validation rejecting `side_effect_ledgers` on worker kinds outside `AGENT_SIDE_EFFECT` and `NOTIFICATION_DELIVERY`.
- **Verification**: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_ledgers_on_non_side_effect_workers -q`
- **Review owner**: parent
- **Status**: [x]

### Task 87 — Wake channels are non-blank

- **File(s)**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 86
- **Touch set**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/worker_manifest.py` for wake-channel validation semantics.
- **Failing test first**: `tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_wake_channels` — patch a manifest to add a blank `wakes_out` channel and assert manifest validation raises a dedicated wake-channel error.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `wakes_on` and `wakes_out` channel declarations must not be blank before listener, NOTIFY, or worker inventory harnesses can treat wake topology as source truth.
- **On-demand context**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, Worker Inventory Wake-in/Wake-out checks, and `WakeBus` notify-channel docs checks.
- **Kill/defer criteria**: Stop if blank wake channels are intentionally supported as placeholders, if validation only relies on Worker Inventory docs comparison, or if the fix touches dirty worker runtime contract files.
- **Eval/repair signal**: blank wake channel, listener/notify topology placeholder, Worker Inventory wake drift, manifest validation drift, and SDD generated index drift.
- **Implementation**: Add manifest validation rejecting blank strings in `wakes_on` and `wakes_out`.
- **Verification**: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_wake_channels -q`
- **Review owner**: parent
- **Status**: [x]

### Task 88 — Wake channels are unique per worker field

- **File(s)**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 87
- **Touch set**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/worker_manifest.py` for wake-channel validation semantics.
- **Failing test first**: `tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_wake_channels` — patch a manifest to repeat a `wakes_on` channel and assert manifest validation raises a dedicated wake-channel duplication error.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `wakes_on` and `wakes_out` channel declarations must not repeat a channel within the same worker field before listener, NOTIFY, or worker inventory harnesses can treat wake topology as source truth.
- **On-demand context**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, Worker Inventory Wake-in/Wake-out checks, and `WakeBus` notify-channel docs checks.
- **Kill/defer criteria**: Stop if duplicate wake channels are intentionally supported for weighting or repeated wake waits, if validation only relies on Worker Inventory docs comparison, or if the fix touches dirty worker runtime contract files.
- **Eval/repair signal**: duplicate wake channel, listener/notify topology duplication, stale repeated wake breadcrumb, manifest validation drift, and SDD generated index drift.
- **Implementation**: Add manifest validation rejecting duplicate strings in `wakes_on` and `wakes_out`.
- **Verification**: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_wake_channels -q`
- **Review owner**: parent
- **Status**: [x]

### Task 89 — Advisory lock keys are unique

- **File(s)**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 88
- **Touch set**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/worker_manifest.py` for advisory-lock validation semantics.
- **Failing test first**: `tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_advisory_lock_keys` — patch two locked manifests to share one `advisory_lock_key` and assert manifest validation raises a dedicated advisory-lock duplication error.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Non-empty `advisory_lock_key` declarations must be globally unique before runtime lifecycle, advisory-lock, or worker inventory harnesses can treat lock ownership as source truth.
- **On-demand context**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `WorkerBase._ensure_advisory_lock`, `DBPoolBundle.acquire_advisory_lock_connection`, and worker inventory advisory-lock docs.
- **Kill/defer criteria**: Stop if two workers intentionally share one long-lived advisory lock as a documented lifecycle primitive, if validation only checks settings defaults, or if the fix touches dirty worker runtime contract files.
- **Eval/repair signal**: duplicate advisory lock key, single-writer lock collision, lifecycle ownership drift, manifest validation drift, and SDD generated index drift.
- **Implementation**: Add manifest validation rejecting duplicate non-empty `advisory_lock_key` values.
- **Verification**: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_advisory_lock_keys -q`
- **Review owner**: parent
- **Status**: [x]

### Task 90 — Advisory lock keys are non-blank

- **File(s)**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 89
- **Touch set**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/worker_manifest.py` for advisory-lock validation semantics.
- **Failing test first**: `tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_advisory_lock_keys` — patch a locked manifest to declare a blank `advisory_lock_key` and assert manifest validation raises a dedicated advisory-lock blank-key error.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Non-empty `advisory_lock_key` declarations must not be blank before runtime lifecycle, advisory-lock, or worker inventory harnesses can treat lock ownership as source truth.
- **On-demand context**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `WorkerBase._advisory_lock_key`, `DBPoolBundle.acquire_advisory_lock_connection`, and worker inventory advisory-lock docs.
- **Kill/defer criteria**: Stop if blank advisory lock keys are intentionally supported as placeholders, if validation only checks settings defaults, or if the fix touches dirty worker runtime contract files.
- **Eval/repair signal**: blank advisory lock key, whitespace lock placeholder, lifecycle ownership drift, manifest validation drift, and SDD generated index drift.
- **Implementation**: Add manifest validation rejecting blank non-`None` `advisory_lock_key` values.
- **Verification**: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_advisory_lock_keys -q`
- **Review owner**: parent
- **Status**: [x]

### Task 91 — Worker identity fields are non-blank

- **File(s)**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 90
- **Touch set**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/worker_manifest.py` for worker identity validation semantics.
- **Failing test first**: `tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_identity_fields` — patch a manifest to declare a blank `name` and assert manifest validation raises a dedicated identity-field error before registry or docs consumers run.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `WorkerManifest.name`, `domain`, `factory`, and `worker_class` must be non-blank before registry, factory, settings, or worker inventory harnesses can treat worker identity as source truth.
- **On-demand context**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, worker registry helpers, Worker Inventory docs checks, and worker factory construction.
- **Kill/defer criteria**: Stop if anonymous or placeholder worker identity fields are intentionally supported, if validation only checks generated docs, or if the fix touches dirty worker runtime contract files.
- **Eval/repair signal**: blank worker name, anonymous worker identity, unresolvable worker class, factory ownership drift, manifest validation drift, and SDD generated index drift.
- **Implementation**: Add manifest validation rejecting blank `name`, `domain`, `factory`, and `worker_class` values.
- **Verification**: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_identity_fields -q`
- **Review owner**: parent
- **Status**: [x]

### Task 92 — Idempotency evidence is non-blank

- **File(s)**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 91
- **Touch set**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/worker_manifest.py` for idempotency evidence validation semantics.
- **Failing test first**: `tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_idempotency_evidence` — patch a manifest to add a blank `idempotency_evidence` entry and assert manifest validation raises a dedicated evidence error before lifecycle or review consumers run.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `WorkerManifest.idempotency_evidence` entries must be non-blank before lifecycle, ownership, review, or worker inventory harnesses can treat idempotency evidence as source truth.
- **On-demand context**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, worker lifecycle review gates, Worker Inventory docs checks, and idempotency evidence rules.
- **Kill/defer criteria**: Stop if blank idempotency evidence is intentionally supported as a placeholder, if validation only checks tuple length, or if the fix touches dirty worker runtime contract files.
- **Eval/repair signal**: blank idempotency evidence, placeholder lifecycle proof, review gate drift, manifest validation drift, and SDD generated index drift.
- **Implementation**: Add manifest validation rejecting blank `idempotency_evidence` entries.
- **Verification**: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_idempotency_evidence -q`
- **Review owner**: parent
- **Status**: [x]

### Task 93 — Input contracts are non-empty

- **File(s)**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 92
- **Touch set**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/worker_manifest.py` for input-contract validation semantics.
- **Failing test first**: `tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_empty_input_contracts` — patch a manifest to declare an empty `input_contract` and assert manifest validation raises before registry, factory, settings, or docs consumers run.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `WorkerManifest.input_contract` must include at least one entry before registry, factory, settings, or worker inventory harnesses can treat worker inputs as source truth.
- **On-demand context**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, worker registry helpers, Worker Inventory docs checks, and worker factory construction.
- **Kill/defer criteria**: Stop if input-less workers are intentionally supported as a documented lifecycle primitive, if validation only checks generated docs, or if the fix touches dirty worker runtime contract files.
- **Eval/repair signal**: empty input contract, anonymous input boundary, factory ownership drift, manifest validation drift, and SDD generated index drift.
- **Implementation**: Add manifest validation rejecting empty `input_contract` declarations.
- **Verification**: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_empty_input_contracts -q`
- **Review owner**: parent
- **Status**: [x]

### Task 94 — Input contracts are non-blank

- **File(s)**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 93
- **Touch set**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/worker_manifest.py` for input-contract validation semantics.
- **Failing test first**: `tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_input_contracts` — patch a manifest to add a blank `input_contract` entry and assert manifest validation raises before registry, factory, settings, or docs consumers run.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `WorkerManifest.input_contract` entries must be non-blank before registry, factory, settings, or worker inventory harnesses can treat worker inputs as source truth.
- **On-demand context**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, worker registry helpers, Worker Inventory docs checks, and worker factory construction.
- **Kill/defer criteria**: Stop if blank input contracts are intentionally supported as placeholders, if validation only checks tuple length, or if the fix touches dirty worker runtime contract files.
- **Eval/repair signal**: blank input contract, whitespace input boundary, factory ownership drift, manifest validation drift, and SDD generated index drift.
- **Implementation**: Add manifest validation rejecting blank `input_contract` entries.
- **Verification**: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_input_contracts -q`
- **Review owner**: parent
- **Status**: [x]

### Task 95 — Ordering keys are non-empty

- **File(s)**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 94
- **Touch set**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/worker_manifest.py` for ordering-key validation semantics.
- **Failing test first**: `tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_empty_ordering_keys` — patch a manifest to declare empty `ordering_keys` and assert manifest validation raises before lifecycle, idempotency, registry, factory, settings, or docs consumers run.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `WorkerManifest.ordering_keys` must include at least one entry before lifecycle, idempotency, registry, factory, settings, or worker inventory harnesses can treat worker ordering as source truth.
- **On-demand context**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, worker lifecycle/idempotency review checks, Worker Inventory docs checks, and worker factory construction.
- **Kill/defer criteria**: Stop if ordering-key-less workers are intentionally supported as a documented lifecycle primitive, if validation only checks generated docs, or if the fix touches dirty worker runtime contract files.
- **Eval/repair signal**: empty ordering keys, anonymous ordering boundary, idempotency review drift, manifest validation drift, and SDD generated index drift.
- **Implementation**: Add manifest validation rejecting empty `ordering_keys` declarations.
- **Verification**: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_empty_ordering_keys -q`
- **Review owner**: parent
- **Status**: [x]

### Task 96 — Ordering keys are non-blank

- **File(s)**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 95
- **Touch set**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/worker_manifest.py` for ordering-key validation semantics.
- **Failing test first**: `tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_ordering_keys` — patch a manifest to add a blank `ordering_keys` entry and assert manifest validation raises before lifecycle, idempotency, registry, factory, settings, or docs consumers run.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `WorkerManifest.ordering_keys` entries must be non-blank before lifecycle, idempotency, registry, factory, settings, or worker inventory harnesses can treat worker ordering as source truth.
- **On-demand context**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, worker lifecycle/idempotency review checks, Worker Inventory docs checks, and worker factory construction.
- **Kill/defer criteria**: Stop if blank ordering keys are intentionally supported as placeholders, if validation only checks tuple length, or if the fix touches dirty worker runtime contract files.
- **Eval/repair signal**: blank ordering keys, whitespace ordering boundary, idempotency review drift, manifest validation drift, and SDD generated index drift.
- **Implementation**: Add manifest validation rejecting blank `ordering_keys` entries.
- **Verification**: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_ordering_keys -q`
- **Review owner**: parent
- **Status**: [x]

### Task 97 — Ordering keys are unique

- **File(s)**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 96
- **Touch set**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/worker_manifest.py` for ordering-key validation semantics.
- **Failing test first**: `tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_ordering_keys` — patch a manifest to repeat one `ordering_keys` entry and assert manifest validation raises before lifecycle, idempotency, registry, factory, settings, or docs consumers run.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `WorkerManifest.ordering_keys` entries must be unique within a manifest before lifecycle, idempotency, registry, factory, settings, or worker inventory harnesses can treat worker ordering as source truth.
- **On-demand context**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, worker lifecycle/idempotency review checks, Worker Inventory docs checks, and worker factory construction.
- **Kill/defer criteria**: Stop if repeated ordering keys are intentionally supported as a documented lifecycle primitive, if validation only checks generated docs, or if the fix touches dirty worker runtime contract files.
- **Eval/repair signal**: duplicate ordering keys, repeated ordering boundary, idempotency review drift, manifest validation drift, and SDD generated index drift.
- **Implementation**: Add manifest validation rejecting duplicate `ordering_keys` entries.
- **Verification**: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_ordering_keys -q`
- **Review owner**: parent
- **Status**: [x]

### Task 98 — Input contracts are unique

- **File(s)**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 97
- **Touch set**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/worker_manifest.py` for input-contract validation semantics.
- **Failing test first**: `tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_input_contracts` — patch a manifest to repeat one `input_contract` entry and assert manifest validation raises before registry, factory, settings, or docs consumers run.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `WorkerManifest.input_contract` entries must be unique within a manifest before registry, factory, settings, or worker inventory harnesses can treat worker inputs as source truth.
- **On-demand context**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, worker registry helpers, Worker Inventory docs checks, and worker factory construction.
- **Kill/defer criteria**: Stop if repeated input contracts are intentionally supported as a documented lifecycle primitive, if validation only checks generated docs, or if the fix touches dirty worker runtime contract files.
- **Eval/repair signal**: duplicate input contract, repeated input boundary, factory ownership drift, manifest validation drift, and SDD generated index drift.
- **Implementation**: Add manifest validation rejecting duplicate `input_contract` entries.
- **Verification**: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_input_contracts -q`
- **Review owner**: parent
- **Status**: [x]

### Task 99 — Idempotency evidence is unique

- **File(s)**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 98
- **Touch set**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/worker_manifest.py` for idempotency evidence validation semantics.
- **Failing test first**: `tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_idempotency_evidence` — patch a manifest to repeat one `idempotency_evidence` entry and assert manifest validation raises before lifecycle, ownership, review, or docs consumers run.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `WorkerManifest.idempotency_evidence` entries must be unique within a manifest before lifecycle, ownership, review, or worker inventory harnesses can treat idempotency evidence as source truth.
- **On-demand context**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, worker lifecycle review gates, Worker Inventory docs checks, and idempotency evidence rules.
- **Kill/defer criteria**: Stop if repeated idempotency evidence is intentionally supported as a documented lifecycle primitive, if validation only checks generated docs, or if the fix touches dirty worker runtime contract files.
- **Eval/repair signal**: duplicate idempotency evidence, repeated lifecycle proof, review gate drift, manifest validation drift, and SDD generated index drift.
- **Implementation**: Add manifest validation rejecting duplicate `idempotency_evidence` entries.
- **Verification**: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_idempotency_evidence -q`
- **Review owner**: parent
- **Status**: [x]

### Task 100 — Worker runtime classes are unique

- **File(s)**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 99
- **Touch set**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/worker_manifest.py` for worker identity validation semantics.
- **Failing test first**: `tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_worker_classes` — patch one manifest to reuse another manifest's `worker_class` and assert manifest validation raises before registry, factory, settings, or docs consumers run.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `WorkerManifest.worker_class` values must be unique across manifests before registry, factory, settings, or worker inventory harnesses can treat worker runtime identity as source truth.
- **On-demand context**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, worker registry helpers, Worker Inventory docs checks, and worker factory construction.
- **Kill/defer criteria**: Stop if two manifest workers are intentionally supported on the same runtime class, if validation only checks generated docs, or if the fix touches dirty worker runtime contract files.
- **Eval/repair signal**: duplicate worker class, runtime identity alias, factory ownership drift, manifest validation drift, and SDD generated index drift.
- **Implementation**: Add manifest validation rejecting duplicate `worker_class` declarations.
- **Verification**: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_worker_classes -q`
- **Review owner**: parent
- **Status**: [x]

### Task 101 — Worker start priorities are non-negative

- **File(s)**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 100
- **Touch set**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/worker_manifest.py` for scheduler priority validation semantics.
- **Failing test first**: `tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_negative_start_priorities` — patch one manifest to declare negative `start_priority` and assert manifest validation raises before scheduler, registry, settings, or docs consumers run.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `WorkerManifest.start_priority` values must be non-negative before `WorkerScheduler`, registry, settings, or worker inventory harnesses can treat worker start order as source truth.
- **On-demand context**: `src/parallax/app/runtime/worker_manifest.py`, `src/parallax/app/runtime/worker_scheduler.py`, `tests/architecture/test_worker_inventory_contract.py`, and Worker Inventory docs checks.
- **Kill/defer criteria**: Stop if negative start priorities are intentionally supported as a documented scheduler primitive, if validation only checks generated docs, or if the fix touches dirty worker runtime contract files.
- **Eval/repair signal**: negative start priority, startup ordering drift, scheduler priority drift, manifest validation drift, and SDD generated index drift.
- **Implementation**: Add manifest validation rejecting negative `start_priority` values.
- **Verification**: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_negative_start_priorities -q`
- **Review owner**: parent
- **Status**: [x]

### Task 102 — Worker start priorities are integer bands

- **File(s)**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 101
- **Touch set**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/worker_manifest.py` for scheduler priority validation semantics.
- **Failing test first**: `tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_integer_start_priorities` — patch one manifest to declare fractional `start_priority` and assert manifest validation raises before scheduler, registry, settings, or docs consumers run.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `WorkerManifest.start_priority` values must be strict integer bands before `WorkerScheduler`, registry, settings, or worker inventory harnesses can treat worker start order as source truth.
- **On-demand context**: `src/parallax/app/runtime/worker_manifest.py`, `src/parallax/app/runtime/worker_scheduler.py`, `tests/architecture/test_worker_inventory_contract.py`, and Worker Inventory docs checks.
- **Kill/defer criteria**: Stop if fractional start priorities are intentionally supported as a documented scheduler primitive, if validation only checks generated docs, or if the fix touches dirty worker runtime contract files.
- **Eval/repair signal**: fractional start priority, startup ordering drift, scheduler priority drift, manifest validation drift, and SDD generated index drift.
- **Implementation**: Add manifest validation rejecting non-integer `start_priority` values.
- **Verification**: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_integer_start_priorities -q`
- **Review owner**: parent
- **Status**: [x]

### Task 103 — Worker factories are real source files

- **File(s)**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 102
- **Touch set**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/worker_manifest.py` for worker factory source-file validation semantics.
- **Failing test first**: `tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_missing_factory_modules` — patch one manifest to declare missing `factory` and assert manifest validation raises before registry, factory, settings, or docs consumers run.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `WorkerManifest.factory` values must name source files under `src/parallax/app/runtime/worker_factories` before registries, settings, or worker inventory harnesses can treat worker factory ownership as source truth.
- **On-demand context**: `src/parallax/app/runtime/worker_manifest.py`, `src/parallax/app/runtime/worker_factories`, `tests/architecture/test_worker_inventory_contract.py`, and Worker Inventory docs checks.
- **Kill/defer criteria**: Stop if manifest factories intentionally support generated, remote, or non-source factory names, if validation only checks generated docs, or if the fix touches dirty worker runtime contract files.
- **Eval/repair signal**: missing worker factory module, factory ownership drift, registry drift, manifest validation drift, and SDD generated index drift.
- **Implementation**: Add manifest validation rejecting `factory` values that do not resolve to an existing worker factory source file.
- **Verification**: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_missing_factory_modules -q`
- **Review owner**: parent
- **Status**: [x]

### Task 104 — Worker class modules resolve

- **File(s)**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 103
- **Touch set**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/worker_manifest.py` for worker class module validation semantics.
- **Failing test first**: `tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_missing_worker_class_modules` — patch one manifest to declare missing `worker_class` module and assert manifest validation raises before registry, factory, settings, or docs consumers run.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `WorkerManifest.worker_class` values must expose a resolvable module path before registries, settings, or worker inventory harnesses can treat worker runtime ownership as source truth.
- **On-demand context**: `src/parallax/app/runtime/worker_manifest.py`, `src/parallax/domains/*/runtime`, `tests/architecture/test_worker_inventory_contract.py`, and Worker Inventory docs checks.
- **Kill/defer criteria**: Stop if worker class declarations intentionally support generated, remote, or lazy non-importable module paths, if validation only checks generated docs, or if the fix touches dirty worker runtime contract files.
- **Eval/repair signal**: missing worker class module, runtime implementation drift, registry drift, manifest validation drift, and SDD generated index drift.
- **Implementation**: Add manifest validation rejecting `worker_class` values whose module path cannot be resolved.
- **Verification**: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_missing_worker_class_modules -q`
- **Review owner**: parent
- **Status**: [x]

### Task 105 — Worker class names resolve

- **File(s)**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 104
- **Touch set**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/worker_manifest.py` for worker class symbol validation semantics.
- **Failing test first**: `tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_missing_worker_class_names` — patch one manifest to declare missing class name inside an existing `worker_class` module and assert manifest validation raises before registry, factory, settings, or docs consumers run.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `WorkerManifest.worker_class` values must resolve to an existing class symbol before registries, settings, or worker inventory harnesses can treat worker runtime ownership as source truth.
- **On-demand context**: `src/parallax/app/runtime/worker_manifest.py`, `src/parallax/domains/*/runtime`, `tests/architecture/test_worker_inventory_contract.py`, and Worker Inventory docs checks.
- **Kill/defer criteria**: Stop if worker class declarations intentionally support generated, remote, or lazy missing symbols, if validation only checks generated docs, or if the fix touches dirty worker runtime contract files.
- **Eval/repair signal**: missing worker class symbol, runtime implementation drift, registry drift, manifest validation drift, and SDD generated index drift.
- **Implementation**: Add manifest validation rejecting `worker_class` values whose class name is absent from the resolved module.
- **Verification**: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_missing_worker_class_names -q`
- **Review owner**: parent
- **Status**: [x]

### Task 106 — Worker domains are real source directories

- **File(s)**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 105
- **Touch set**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/worker_manifest.py` for worker domain source-directory validation semantics.
- **Failing test first**: `tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_missing_domain_directories` — patch one manifest to declare missing `domain` and assert manifest validation raises before registry, factory, settings, or docs consumers run.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `WorkerManifest.domain` values must name existing `src/parallax/domains/<domain>` source directories before registries, settings, or worker inventory harnesses can treat bounded-context ownership as source truth.
- **On-demand context**: `src/parallax/app/runtime/worker_manifest.py`, `src/parallax/domains`, `tests/architecture/test_worker_inventory_contract.py`, and Worker Inventory docs checks.
- **Kill/defer criteria**: Stop if worker domains intentionally support generated, remote, or non-source domain names, if validation only checks generated docs, or if the fix touches dirty worker runtime contract files.
- **Eval/repair signal**: missing worker domain directory, bounded-context ownership drift, registry drift, manifest validation drift, and SDD generated index drift.
- **Implementation**: Add manifest validation rejecting `domain` values that do not resolve to an existing source domain directory.
- **Verification**: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_missing_domain_directories -q`
- **Review owner**: parent
- **Status**: [x]

### Task 107 — Worker classifications are enum-owned

- **File(s)**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 106
- **Touch set**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/worker_manifest.py` for worker classification enum validation semantics.
- **Failing test first**: `tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_raw_classification_values` — patch one manifest to declare raw string `lane` and assert manifest validation raises before scheduler, registry, factory, settings, or docs consumers run.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `WorkerManifest.lane`, `WorkerManifest.kind`, and `WorkerManifest.runtime_constraint` values must be enum members before scheduler ordering, runtime lifecycle, settings, or worker inventory harnesses can treat classifications as source truth.
- **On-demand context**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, and Worker Inventory docs checks.
- **Kill/defer criteria**: Stop if manifest classification intentionally supports raw string compatibility values, if validation only checks generated docs, or if the fix touches dirty worker runtime contract files.
- **Eval/repair signal**: raw worker classification value, runtime constraint drift, scheduler classification drift, manifest validation drift, and SDD generated index drift.
- **Implementation**: Add manifest validation rejecting `lane`, `kind`, or `runtime_constraint` values that are not their manifest enum types.
- **Verification**: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_raw_classification_values -q`
- **Review owner**: parent
- **Status**: [x]

### Task 108 — Provider I/O flags are boolean

- **File(s)**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 107
- **Touch set**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/worker_manifest.py` for provider I/O flag validation semantics.
- **Failing test first**: `tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_boolean_provider_io_flags` — patch one manifest to declare truthy string `uses_provider_io` and assert manifest validation raises before provider-boundary, registry, settings, or docs consumers run.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `WorkerManifest.uses_provider_io` values must be strict booleans before provider-boundary, registry, settings, or worker inventory harnesses can treat external-data boundaries as source truth.
- **On-demand context**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, and Worker Inventory docs checks.
- **Kill/defer criteria**: Stop if provider I/O intentionally supports truthy compatibility values, if validation only checks generated docs, or if the fix touches dirty worker runtime contract files.
- **Eval/repair signal**: truthy provider I/O flag, provider-boundary masking, manifest validation drift, and SDD generated index drift.
- **Implementation**: Add manifest validation rejecting non-boolean `uses_provider_io` values.
- **Verification**: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_boolean_provider_io_flags -q`
- **Review owner**: parent
- **Status**: [x]

### Task 109 — Tuple manifest contracts reject compatibility lists

- **File(s)**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 108
- **Touch set**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/worker_manifest.py` for tuple-valued manifest contract validation semantics.
- **Failing test first**: `tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_tuple_contract_fields` — patch one manifest to declare list-shaped `input_contract` and assert manifest validation raises before registry, factory, settings, or docs consumers run.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: tuple-valued `WorkerManifest` contract fields must be strict tuples before registry, factory, settings, or worker inventory harnesses can treat contract declarations as immutable source truth.
- **On-demand context**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, and Worker Inventory docs checks.
- **Kill/defer criteria**: Stop if tuple-valued manifest contracts intentionally support list compatibility values, if validation only checks generated docs, or if the fix touches dirty worker runtime contract files.
- **Eval/repair signal**: list-shaped manifest contract field, mutable contract drift, manifest validation drift, and SDD generated index drift.
- **Implementation**: Add manifest validation rejecting non-tuple values for tuple-valued contract fields.
- **Verification**: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_tuple_contract_fields -q`
- **Review owner**: parent
- **Status**: [x]

### Task 110 — Tuple string contracts reject non-string entries

- **File(s)**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 109
- **Touch set**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/worker_manifest.py` for tuple-valued manifest entry validation semantics.
- **Failing test first**: `tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_string_contract_entries` — patch one manifest to declare numeric `input_contract` entry and assert manifest validation raises before blank, duplicate, registry, factory, settings, or docs consumers run.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: tuple-valued string `WorkerManifest` contract fields must contain only strings before blank, duplicate, ownership, wake-channel, registry, factory, settings, or worker inventory harnesses can treat contract declarations as source truth.
- **On-demand context**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, and Worker Inventory docs checks.
- **Kill/defer criteria**: Stop if tuple-valued string manifest contracts intentionally support non-string compatibility values, if validation only checks generated docs, or if the fix touches dirty worker runtime contract files.
- **Eval/repair signal**: non-string manifest contract entry, implementation-detail AttributeError, manifest validation drift, and SDD generated index drift.
- **Implementation**: Add manifest validation rejecting non-string entries inside tuple-valued string contract fields.
- **Verification**: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_string_contract_entries -q`
- **Review owner**: parent
- **Status**: [x]

### Task 111 — Read-model identity columns are tuples

- **File(s)**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 110
- **Touch set**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/worker_manifest.py` for stable read-model identity column tuple validation semantics.
- **Failing test first**: `tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_tuple_read_model_identity_columns` — patch one manifest to declare list-shaped stable identity columns and assert manifest validation raises before ownership, registry, factory, settings, or docs consumers run.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `WorkerManifest.current_read_model_identities` identity columns must be strict tuples before ownership, registry, factory, settings, or worker inventory harnesses can treat serving identity declarations as immutable source truth.
- **On-demand context**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, and Worker Inventory docs checks.
- **Kill/defer criteria**: Stop if stable identity columns intentionally support list compatibility values, if validation only checks generated docs, or if the fix touches dirty worker runtime contract files.
- **Eval/repair signal**: list-shaped stable identity columns, serving identity drift, manifest validation drift, and SDD generated index drift.
- **Implementation**: Add manifest validation rejecting non-tuple identity columns inside `current_read_model_identities`.
- **Verification**: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_tuple_read_model_identity_columns -q`
- **Review owner**: parent
- **Status**: [x]

### Task 112 — Read-model identity entries are tuples

- **File(s)**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 111
- **Touch set**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/worker_manifest.py` for stable read-model identity entry tuple validation semantics.
- **Failing test first**: `tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_tuple_read_model_identity_entries` — patch one manifest to declare a list-shaped stable identity entry and assert manifest validation raises before ownership, registry, factory, settings, or docs consumers run.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `WorkerManifest.current_read_model_identities` entries must be strict tuples before ownership, registry, factory, settings, or worker inventory harnesses can treat serving identity declarations as immutable source truth.
- **On-demand context**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, and Worker Inventory docs checks.
- **Kill/defer criteria**: Stop if stable identity entries intentionally support list compatibility values, if validation only checks generated docs, or if the fix touches dirty worker runtime contract files.
- **Eval/repair signal**: list-shaped stable identity entries, serving identity drift, manifest validation drift, and SDD generated index drift.
- **Implementation**: Add manifest validation rejecting non-tuple entries inside `current_read_model_identities` before table/column unpacking.
- **Verification**: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_tuple_read_model_identity_entries -q`
- **Review owner**: parent
- **Status**: [x]

### Task 113 — Worker manifest import dependency is explicit

- **File(s)**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_src_domain_architecture.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 112
- **Touch set**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_src_domain_architecture.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/worker_manifest.py` for manifest import dependency semantics.
- **Failing test first**: `tests/architecture/test_src_domain_architecture.py::test_worker_manifest_imports_in_clean_process_without_importlib_util_side_effect` — import `worker_manifest.py` in a clean subprocess after removing incidental `importlib.util` from the package object and assert import succeeds.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `worker_manifest.py` must import `importlib.util` directly before manifest validation calls `find_spec`, so source-owned worker harnesses do not rely on prior import side effects.
- **On-demand context**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_src_domain_architecture.py`, and Worker Manifest validation helpers.
- **Kill/defer criteria**: Stop if Python import semantics intentionally guarantee `importlib.util` on the package object for all supported runtimes, if the fix masks import errors broadly, or if the change touches worker runtime behavior outside manifest import dependencies.
- **Eval/repair signal**: clean-process import failure, `AttributeError: module 'importlib' has no attribute 'util'`, manifest validation import drift, and SDD generated index drift.
- **Implementation**: Add an explicit `import importlib.util` dependency in `worker_manifest.py`.
- **Verification**: `uv run pytest tests/architecture/test_src_domain_architecture.py::test_worker_manifest_imports_in_clean_process_without_importlib_util_side_effect -q`
- **Review owner**: parent
- **Status**: [x]

### Task 114 — Read-model identity entries are pairs

- **File(s)**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 113
- **Touch set**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/worker_manifest.py` for stable read-model identity entry arity validation semantics.
- **Failing test first**: `tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_malformed_read_model_identity_entries` — patch one manifest to declare a three-field stable identity entry and assert manifest validation raises before Python table/column unpacking errors leak.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `WorkerManifest.current_read_model_identities` entries must be exactly `(table_name, identity_columns)` pairs before ownership, registry, factory, settings, or worker inventory harnesses can treat serving identity declarations as immutable source truth.
- **On-demand context**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, and Worker Inventory docs checks.
- **Kill/defer criteria**: Stop if stable identity entries intentionally support compatibility metadata fields, if validation only checks generated docs, or if the fix touches dirty worker runtime contract files.
- **Eval/repair signal**: malformed stable identity entry arity, implementation-detail tuple unpacking errors, manifest validation drift, and SDD generated index drift.
- **Implementation**: Add manifest validation rejecting `current_read_model_identities` entries whose tuple arity is not exactly two before table/column unpacking.
- **Verification**: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_malformed_read_model_identity_entries -q`
- **Review owner**: parent
- **Status**: [x]

### Task 115 — Root visual artifacts are rejected

- **File(s)**: `tests/architecture/test_harness_structure.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 114
- **Touch set**: `tests/architecture/test_harness_structure.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Removed file(s)**: `news-provider-rating-1366.png`, `parallax-macro-assets-after-1366.png`, `parallax-macro-assets-after-390.png`, `parallax-macro-assets-before-1366.png`, `parallax-macro-assets-before-390.png`, `timsun-assets-1366.png`
- **Conflict set**: coordinate with `tests/architecture/test_harness_structure.py` for root artifact hygiene semantics.
- **Failing test first**: `tests/architecture/test_harness_structure.py::test_repo_root_has_no_loose_visual_artifacts` — run the new harness against a temporary HEAD workspace with root PNG artifacts still present and assert it fails on those loose files.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Visual verification artifacts must live under owned artifact directories such as `.codex_artifacts/`, `docs/generated/`, `docs/mockups/`, or `output/playwright/`, never as loose repository-root files.
- **On-demand context**: `tests/architecture/test_harness_structure.py`, `docs/generated/README.md`, and current tracked root visual artifacts.
- **Kill/defer criteria**: Stop if a root visual artifact is intentionally part of public product packaging, if it is referenced by docs/source, or if the harness cannot distinguish root files from owned artifact directories.
- **Eval/repair signal**: root PNG/JPG/WEBP/GIF files, stale visual verification screenshots, repository-root artifact drift, and SDD generated index drift.
- **Implementation**: Add an architecture harness rejecting loose root-level visual files and remove the existing root PNG artifacts.
- **Verification**: `uv run pytest tests/architecture/test_harness_structure.py::test_repo_root_has_no_loose_visual_artifacts -q`
- **Review owner**: parent
- **Status**: [x]

### Task 116 — Worker queue-depth tables are strings

- **File(s)**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 115
- **Touch set**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/worker_manifest.py` for queue-depth table type validation semantics.
- **Failing test first**: `tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_string_queue_depth_tables` — patch one manifest to declare numeric `queue_depth_table` and assert manifest validation raises before table-name `.strip()` errors leak.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `WorkerManifest.queue_depth_table` must be `None` or strict `str` before table hygiene, queue ownership, queue-health, registry, settings, or worker inventory harnesses consume it.
- **On-demand context**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, and queue-health Worker Inventory docs checks.
- **Kill/defer criteria**: Stop if queue-depth table declarations intentionally support compatibility metadata objects, if validation only checks generated docs, or if the fix touches worker queue runtime behavior.
- **Eval/repair signal**: non-string queue-depth table declarations, implementation-detail table-name attribute errors, queue-health harness drift, and SDD generated index drift.
- **Implementation**: Add manifest validation rejecting non-string `queue_depth_table` values before table hygiene and ownership checks.
- **Verification**: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_string_queue_depth_tables -q`
- **Review owner**: parent
- **Status**: [x]

### Task 117 — Worker advisory lock keys are strings

- **File(s)**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 116
- **Touch set**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/worker_manifest.py` for advisory-lock key type validation semantics.
- **Failing test first**: `tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_string_advisory_lock_keys` — patch one manifest to declare numeric `advisory_lock_key` and assert manifest validation raises before lock-key `.strip()` errors leak.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `WorkerManifest.advisory_lock_key` must be `None` or strict `str` before advisory-lock blank checks, duplicate checks, lifecycle, registry, settings, or worker inventory harnesses consume it.
- **On-demand context**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, and worker lifecycle advisory-lock harness checks.
- **Kill/defer criteria**: Stop if advisory-lock declarations intentionally support compatibility metadata objects, if validation only checks generated docs, or if the fix touches runtime lock acquisition behavior.
- **Eval/repair signal**: non-string advisory-lock declarations, implementation-detail lock-key attribute errors, worker lifecycle harness drift, and SDD generated index drift.
- **Implementation**: Add manifest validation rejecting non-string `advisory_lock_key` values before blank and duplicate lock checks.
- **Verification**: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_string_advisory_lock_keys -q`
- **Review owner**: parent
- **Status**: [x]

### Task 118 — Worker identity fields are strings

- **File(s)**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 117
- **Touch set**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/worker_manifest.py` for worker identity field type validation semantics.
- **Failing test first**: `tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_string_identity_fields` — patch worker identity fields to numeric values and assert manifest validation raises before `.strip()`, `Path`, or import errors leak.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `WorkerManifest.name`, `domain`, `factory`, and `worker_class` must be strict `str` before identity blank checks, source-path checks, class import checks, registry, settings, or worker inventory harnesses consume them.
- **On-demand context**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, and Worker Inventory registry/docs checks.
- **Kill/defer criteria**: Stop if worker identity fields intentionally support compatibility objects, if validation only checks generated docs, or if the fix touches worker factory/runtime behavior.
- **Eval/repair signal**: non-string worker identity declarations, implementation-detail identity-field attribute/path/import errors, registry harness drift, and SDD generated index drift.
- **Implementation**: Add manifest validation rejecting non-string `name`, `domain`, `factory`, and `worker_class` values before blank and source-path checks.
- **Verification**: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_string_identity_fields -q`
- **Review owner**: parent
- **Status**: [x]

### Task 119 — Read-model identity tables are strings

- **File(s)**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 118
- **Touch set**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/worker_manifest.py` for stable read-model identity table type validation semantics.
- **Failing test first**: `tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_string_read_model_identity_tables` — patch one `current_read_model_identities` table name to a numeric value and assert manifest validation raises before table-name `.strip()` errors leak.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `WorkerManifest.current_read_model_identities` table names must be strict `str` before blank, duplicate, missing-identity, ownership, registry, settings, or worker inventory harnesses consume stable serving identity declarations.
- **On-demand context**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, and current read-model writer/identity ownership checks.
- **Kill/defer criteria**: Stop if stable read-model identity table names intentionally support compatibility objects, if validation only checks generated docs, or if the fix touches projection runtime behavior.
- **Eval/repair signal**: non-string stable identity table names, implementation-detail table-name attribute errors, serving identity harness drift, and SDD generated index drift.
- **Implementation**: Add manifest validation rejecting non-string table names inside `current_read_model_identities` before blank and ownership checks.
- **Verification**: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_string_read_model_identity_tables -q`
- **Review owner**: parent
- **Status**: [x]

### Task 120 — Read-model identity columns are strings

- **File(s)**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 119
- **Touch set**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/worker_manifest.py` for stable read-model identity column type validation semantics.
- **Failing test first**: `tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_string_read_model_identity_columns` — patch one `current_read_model_identities` identity column to a numeric value and assert manifest validation raises before column-name `.strip()` errors leak.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `WorkerManifest.current_read_model_identities` identity column names must be strict `str` before blank, duplicate, forbidden lifecycle-column, missing-identity, ownership, registry, settings, or worker inventory harnesses consume stable serving identity declarations.
- **On-demand context**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, and current read-model writer/identity ownership checks.
- **Kill/defer criteria**: Stop if stable read-model identity column names intentionally support compatibility objects, if validation only checks generated docs, or if the fix touches projection runtime behavior.
- **Eval/repair signal**: non-string stable identity column names, implementation-detail column-name attribute errors, serving identity harness drift, and SDD generated index drift.
- **Implementation**: Add manifest validation rejecting non-string identity column names inside `current_read_model_identities` before blank, duplicate, forbidden lifecycle-column, and ownership checks.
- **Verification**: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_string_read_model_identity_columns -q`
- **Review owner**: parent
- **Status**: [x]

### Task 121 — Publisher identity columns are strings

- **File(s)**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 120
- **Touch set**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/current_read_model_publisher.py` for stable publisher identity column type validation semantics.
- **Failing test first**: `tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_run_generation_identity_and_skips_unchanged` — construct `CurrentReadModelPublisher` with a numeric stable identity column and assert publisher validation raises before column-name `.strip()` errors leak.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `CurrentReadModelPublisher.identity_columns` entries must be strict `str` before blank, duplicate, forbidden lifecycle-column, row identity, changed-row hashing, or worker static harnesses consume stable serving identity declarations.
- **On-demand context**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, and stable current read-model identity contracts.
- **Kill/defer criteria**: Stop if publisher identity columns intentionally support compatibility objects, if validation only checks manifest declarations, or if the fix touches projection worker runtime behavior.
- **Eval/repair signal**: non-string publisher identity column names, implementation-detail column-name attribute errors, publisher/manifest validation drift, and SDD generated index drift.
- **Implementation**: Add publisher construction validation rejecting non-string identity column names before blank, duplicate, forbidden lifecycle-column, row identity, and changed-row hashing checks.
- **Verification**: `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_run_generation_identity_and_skips_unchanged -q`
- **Review owner**: parent
- **Status**: [x]

### Task 122 — Publisher payload hash columns are strings

- **File(s)**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 121
- **Touch set**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/current_read_model_publisher.py` for publisher payload hash column type validation semantics.
- **Failing test first**: `tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_non_string_payload_hash_column` — construct `CurrentReadModelPublisher` with a numeric `payload_hash_column` and assert publisher validation raises before row hashing or changed-row writes can use it as a serving-row key.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `CurrentReadModelPublisher.payload_hash_column` must be strict `str` before row payload hashing, changed-row writes, or worker static harnesses consume it as the serving-row payload hash key.
- **On-demand context**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, and stable current read-model publisher contracts.
- **Kill/defer criteria**: Stop if publisher payload hash columns intentionally support compatibility objects, if validation only checks caller code, or if the fix touches projection worker runtime behavior.
- **Eval/repair signal**: non-string publisher payload hash column names, silent invalid serving-row hash keys, publisher validation drift, and SDD generated index drift.
- **Implementation**: Add publisher construction validation rejecting non-string `payload_hash_column` values before row payload hashing and changed-row write checks.
- **Verification**: `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_non_string_payload_hash_column -q`
- **Review owner**: parent
- **Status**: [x]

### Task 123 — Publisher payload columns are tuples

- **File(s)**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 122
- **Touch set**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/current_read_model_publisher.py` for publisher payload column tuple validation semantics.
- **Failing test first**: `tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_non_tuple_payload_columns` — construct `CurrentReadModelPublisher` with list-shaped `payload_columns` and assert publisher validation raises before payload hashing can treat compatibility lists as payload field declarations.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `CurrentReadModelPublisher.payload_columns` must be `None` or a tuple before row payload hashing, changed-row writes, or worker static harnesses consume it as the payload field list.
- **On-demand context**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, and stable current read-model publisher contracts.
- **Kill/defer criteria**: Stop if publisher payload columns intentionally support compatibility lists or scalar strings, if validation only checks caller code, or if the fix touches projection worker runtime behavior.
- **Eval/repair signal**: list-shaped publisher payload columns, scalar-string payload column iteration, silent payload hash drift, publisher validation drift, and SDD generated index drift.
- **Implementation**: Add publisher construction validation rejecting non-tuple `payload_columns` values before row payload hashing and changed-row write checks.
- **Verification**: `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_non_tuple_payload_columns -q`
- **Review owner**: parent
- **Status**: [x]

### Task 124 — Publisher payload column entries are strings

- **File(s)**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 123
- **Touch set**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/current_read_model_publisher.py` for publisher payload column entry type validation semantics.
- **Failing test first**: `tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_non_string_payload_columns` — construct `CurrentReadModelPublisher` with a numeric `payload_columns` entry and assert publisher validation raises before payload hashing can look up invalid payload keys.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `CurrentReadModelPublisher.payload_columns` entries must be strict `str` before row payload hashing, changed-row writes, or worker static harnesses consume them as payload keys.
- **On-demand context**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, and stable current read-model publisher contracts.
- **Kill/defer criteria**: Stop if publisher payload column entries intentionally support compatibility key objects, if validation only checks caller code, or if the fix touches projection worker runtime behavior.
- **Eval/repair signal**: non-string publisher payload column entries, silent invalid payload-key lookups, payload hash drift, publisher validation drift, and SDD generated index drift.
- **Implementation**: Add publisher construction validation rejecting non-string `payload_columns` entries before row payload hashing and changed-row write checks.
- **Verification**: `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_non_string_payload_columns -q`
- **Review owner**: parent
- **Status**: [x]

### Task 125 — Publisher payload column entries are non-blank

- **File(s)**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 124
- **Touch set**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/current_read_model_publisher.py` for publisher payload column blank validation semantics.
- **Failing test first**: `tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_blank_payload_columns` — construct `CurrentReadModelPublisher` with a blank `payload_columns` entry and assert publisher validation raises before payload hashing can look up empty payload keys.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `CurrentReadModelPublisher.payload_columns` entries must be non-blank before row payload hashing, changed-row writes, or worker static harnesses consume them as payload keys.
- **On-demand context**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, and stable current read-model publisher contracts.
- **Kill/defer criteria**: Stop if blank publisher payload column entries intentionally mean optional payload hashing, if validation only checks caller code, or if the fix touches projection worker runtime behavior.
- **Eval/repair signal**: blank publisher payload column entries, empty payload-key lookups, payload hash drift, publisher validation drift, and SDD generated index drift.
- **Implementation**: Add publisher construction validation rejecting blank `payload_columns` entries before row payload hashing and changed-row write checks.
- **Verification**: `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_blank_payload_columns -q`
- **Review owner**: parent
- **Status**: [x]

### Task 126 — Publisher payload hash columns are non-blank

- **File(s)**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 125
- **Touch set**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/current_read_model_publisher.py` for publisher payload hash column blank validation semantics.
- **Failing test first**: `tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_blank_payload_hash_column` — construct `CurrentReadModelPublisher` with a blank `payload_hash_column` and assert publisher validation raises before changed-row writes can add empty serving-row keys.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `CurrentReadModelPublisher.payload_hash_column` must be non-blank before row payload hashing, changed-row writes, or worker static harnesses consume it as the serving-row hash key.
- **On-demand context**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, and stable current read-model publisher contracts.
- **Kill/defer criteria**: Stop if blank publisher payload hash columns intentionally mean caller-owned hash writes, if validation only checks caller code, or if the fix touches projection worker runtime behavior.
- **Eval/repair signal**: blank publisher payload hash column names, empty serving-row hash keys, changed-row write drift, publisher validation drift, and SDD generated index drift.
- **Implementation**: Add publisher construction validation rejecting blank `payload_hash_column` values before row payload hashing and changed-row write checks.
- **Verification**: `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_blank_payload_hash_column -q`
- **Review owner**: parent
- **Status**: [x]

### Task 127 — Publisher payload column entries are unique

- **File(s)**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 126
- **Touch set**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/current_read_model_publisher.py` for publisher payload column duplicate validation semantics.
- **Failing test first**: `tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_duplicate_payload_columns` — construct `CurrentReadModelPublisher` with duplicate `payload_columns` entries and assert publisher validation raises before payload hashing silently collapses repeated payload keys.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `CurrentReadModelPublisher.payload_columns` entries must be unique before row payload hashing, changed-row writes, or worker static harnesses consume them as payload keys.
- **On-demand context**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, and stable current read-model publisher contracts.
- **Kill/defer criteria**: Stop if duplicate publisher payload column entries intentionally mean weighted payload hashing, if validation only checks caller code, or if the fix touches projection worker runtime behavior.
- **Eval/repair signal**: duplicate publisher payload columns, silently collapsed payload keys, payload hash drift, publisher validation drift, and SDD generated index drift.
- **Implementation**: Add publisher construction validation rejecting duplicate `payload_columns` entries before row payload hashing and changed-row write checks.
- **Verification**: `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_duplicate_payload_columns -q`
- **Review owner**: parent
- **Status**: [x]

### Task 128 — Publisher payload hash columns are not lifecycle columns

- **File(s)**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 127
- **Touch set**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/current_read_model_publisher.py` for publisher payload hash lifecycle-column validation semantics.
- **Failing test first**: `tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_lifecycle_payload_hash_column` — construct `CurrentReadModelPublisher` with a lifecycle `payload_hash_column` and assert publisher validation raises before changed-row writes can overwrite runtime lifecycle fields.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `CurrentReadModelPublisher.payload_hash_column` must not be a serving lifecycle column before changed-row writes, worker static harnesses, or row payload hashing consume it as the serving-row hash key.
- **On-demand context**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, and stable current read-model publisher contracts.
- **Kill/defer criteria**: Stop if lifecycle-named publisher payload hash columns intentionally mean lifecycle-field replacement, if validation only checks caller code, or if the fix touches projection worker runtime behavior.
- **Eval/repair signal**: lifecycle publisher payload hash column names, overwritten runtime lifecycle fields, changed-row write drift, publisher validation drift, and SDD generated index drift.
- **Implementation**: Add publisher construction validation rejecting lifecycle `payload_hash_column` values before changed-row write checks.
- **Verification**: `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_lifecycle_payload_hash_column -q`
- **Review owner**: parent
- **Status**: [x]

### Task 129 — Publisher payload columns exclude the payload hash column

- **File(s)**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 128
- **Touch set**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/current_read_model_publisher.py` for publisher payload hash self-reference validation semantics.
- **Failing test first**: `tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_payload_hash_payload_columns` — construct `CurrentReadModelPublisher` with explicit `payload_columns` containing the configured hash column and assert publisher validation raises before row hashing can self-reference prior serving hashes.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `CurrentReadModelPublisher.payload_columns` must not include the configured payload hash column before row payload hashing, changed-row writes, or worker static harnesses consume them as payload keys.
- **On-demand context**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, and stable current read-model publisher contracts.
- **Kill/defer criteria**: Stop if payload hash self-reference is intentionally part of the hash protocol, if validation only checks caller code, or if the fix touches projection worker runtime behavior.
- **Eval/repair signal**: self-referential payload hash columns, prior-hash feedback loops, changed-row drift, publisher validation drift, and SDD generated index drift.
- **Implementation**: Add publisher construction validation rejecting explicit `payload_columns` that contain the configured `payload_hash_column`.
- **Verification**: `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_payload_hash_payload_columns -q`
- **Review owner**: parent
- **Status**: [x]

### Task 130 — Publisher payload columns exclude lifecycle columns

- **File(s)**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 129
- **Touch set**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/current_read_model_publisher.py` for publisher payload lifecycle-column validation semantics.
- **Failing test first**: `tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_lifecycle_payload_columns` — construct `CurrentReadModelPublisher` with explicit lifecycle `payload_columns` and assert publisher validation raises before row hashing can reintroduce run/generation/timestamp drift.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `CurrentReadModelPublisher.payload_columns` must not include serving lifecycle columns before row payload hashing, changed-row writes, or worker static harnesses consume them as payload keys.
- **On-demand context**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, and stable current read-model publisher contracts.
- **Kill/defer criteria**: Stop if explicit lifecycle payload columns intentionally mean attempt/timestamp-sensitive serving hashes, if validation only checks caller code, or if the fix touches projection worker runtime behavior.
- **Eval/repair signal**: lifecycle payload columns, run/generation/timestamp hash drift, changed-row write drift, publisher validation drift, and SDD generated index drift.
- **Implementation**: Add publisher construction validation rejecting explicit `payload_columns` that contain serving lifecycle columns.
- **Verification**: `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_lifecycle_payload_columns -q`
- **Review owner**: parent
- **Status**: [x]

### Task 131 — Publisher payload hash columns are not identity columns

- **File(s)**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 130
- **Touch set**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/current_read_model_publisher.py` for publisher payload hash identity-column validation semantics.
- **Failing test first**: `tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_identity_payload_hash_column` — construct `CurrentReadModelPublisher` with a `payload_hash_column` that overlaps `identity_columns` and assert publisher validation raises before changed-row writes can overwrite serving identity keys.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `CurrentReadModelPublisher.payload_hash_column` must not overlap stable identity columns before changed-row writes, worker static harnesses, or row identity reads consume the row as stable serving truth.
- **On-demand context**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, and stable current read-model publisher contracts.
- **Kill/defer criteria**: Stop if identity-named publisher payload hash columns intentionally mean replacing serving identities with hash keys, if validation only checks caller code, or if the fix touches projection worker runtime behavior.
- **Eval/repair signal**: identity publisher payload hash column names, overwritten serving identity keys, changed-row write drift, publisher validation drift, and SDD generated index drift.
- **Implementation**: Add publisher construction validation rejecting `payload_hash_column` values that overlap `identity_columns`.
- **Verification**: `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_identity_payload_hash_column -q`
- **Review owner**: parent
- **Status**: [x]

### Task 132 — Publisher explicit payload columns must exist in rows

- **File(s)**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 131
- **Touch set**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/current_read_model_publisher.py` for explicit payload row-shape validation semantics.
- **Failing test first**: `tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_missing_explicit_payload_column` — call `row_payload_hash()` with a row missing one declared explicit payload column and assert hashing raises instead of treating the missing field as `None`.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: every explicit `CurrentReadModelPublisher.payload_columns` entry must be present in each row before payload hashing, changed-row writes, or worker static harnesses consume row hashes as serving truth.
- **On-demand context**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, and stable current read-model publisher contracts.
- **Kill/defer criteria**: Stop if missing explicit payload columns intentionally mean nullable payload values, if validation only checks caller code, or if the fix touches projection worker runtime behavior.
- **Eval/repair signal**: missing explicit payload columns, query projection drift, null hash drift, publisher validation drift, and SDD generated index drift.
- **Implementation**: Change explicit payload hashing from `row.get()` to required row indexing so missing declared payload fields raise before hash computation.
- **Verification**: `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_missing_explicit_payload_column -q`
- **Review owner**: parent
- **Status**: [x]

### Task 133 — Bounded provider schedulers do not declare dirty targets

- **File(s)**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 132
- **Touch set**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/worker_manifest.py` for bounded provider scheduler runtime-constraint validation semantics.
- **Failing test first**: `tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_provider_schedulers_with_dirty_targets` — patch a `BOUNDED_PROVIDER_SCHEDULER` manifest to declare `dirty_target_tables` and assert manifest validation raises before provider source adapters can masquerade as dirty-target consumers.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `BOUNDED_PROVIDER_SCHEDULER` manifests must not declare `dirty_target_tables`; dirty-target consumption belongs to explicitly classified dirty-target consumers before lifecycle, queue-health, or inventory harnesses consume the manifest.
- **On-demand context**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, and worker runtime constraint semantics.
- **Kill/defer criteria**: Stop if bounded provider schedulers intentionally consume dirty-target queues, if validation only checks docs, or if the fix touches provider runtime worker behavior.
- **Eval/repair signal**: provider scheduler dirty-target declarations, source adapter masquerading as dirty consumer, runtime classification drift, manifest validation drift, and SDD generated index drift.
- **Implementation**: Add manifest validation rejecting `dirty_target_tables` whenever `runtime_constraint` is `BOUNDED_PROVIDER_SCHEDULER`.
- **Verification**: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_provider_schedulers_with_dirty_targets -q`
- **Review owner**: parent
- **Status**: [x]

### Task 134 — Bounded provider schedulers do not declare queue depth tables

- **File(s)**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 133
- **Touch set**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/worker_manifest.py` for bounded provider scheduler queue-depth validation semantics.
- **Failing test first**: `tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_provider_schedulers_with_queue_depth` — patch a `BOUNDED_PROVIDER_SCHEDULER` manifest to declare `queue_depth_table` and assert manifest validation raises before provider source adapters can masquerade as leased queue consumers.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `BOUNDED_PROVIDER_SCHEDULER` manifests must not declare `queue_depth_table`; leased queue consumption belongs to explicitly classified leased-job consumers before lifecycle, queue-health, or inventory harnesses consume the manifest.
- **On-demand context**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, and worker runtime constraint semantics.
- **Kill/defer criteria**: Stop if bounded provider schedulers intentionally lease queue tables, if validation only checks docs, or if the fix touches provider runtime worker behavior.
- **Eval/repair signal**: provider scheduler queue-depth declarations, source adapter masquerading as leased queue consumer, runtime classification drift, manifest validation drift, and SDD generated index drift.
- **Implementation**: Add manifest validation rejecting `queue_depth_table` whenever `runtime_constraint` is `BOUNDED_PROVIDER_SCHEDULER`.
- **Verification**: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_provider_schedulers_with_queue_depth -q`
- **Review owner**: parent
- **Status**: [x]

### Task 135 — Bounded provider schedulers do not declare queue health tables

- **File(s)**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 134
- **Touch set**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/worker_manifest.py` for bounded provider scheduler queue-health validation semantics.
- **Failing test first**: `tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_provider_schedulers_with_queue_health_tables` — patch a `BOUNDED_PROVIDER_SCHEDULER` manifest to declare `queue_health_tables` and assert manifest validation raises before provider source adapters can masquerade as queue-health consumers.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `BOUNDED_PROVIDER_SCHEDULER` manifests must not declare `queue_health_tables`; queue-health consumption belongs to explicitly classified queue consumers before lifecycle, queue-health, or inventory harnesses consume the manifest.
- **On-demand context**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, and worker runtime constraint semantics.
- **Kill/defer criteria**: Stop if bounded provider schedulers intentionally report queue-health tables, if validation only checks docs, or if the fix touches provider runtime worker behavior.
- **Eval/repair signal**: provider scheduler queue-health declarations, source adapter masquerading as queue-health consumer, runtime classification drift, manifest validation drift, and SDD generated index drift.
- **Implementation**: Add manifest validation rejecting `queue_health_tables` whenever `runtime_constraint` is `BOUNDED_PROVIDER_SCHEDULER`.
- **Verification**: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_provider_schedulers_with_queue_health_tables -q`
- **Review owner**: parent
- **Status**: [x]

### Task 136 — Queue depth tables are control-plane-owned

- **File(s)**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 135
- **Touch set**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/worker_manifest.py` for queue-depth control-plane ownership validation semantics.
- **Failing test first**: `tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_queue_depth_tables_outside_control_plane` — patch a manifest to point `queue_depth_table` at an owned fact table and assert manifest validation raises before facts or read models can masquerade as leased queues.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Queue-depth declarations must be owned through `writes_control_plane`; generic `owned_tables` membership is not sufficient for queue-health harnesses.
- **On-demand context**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, and worker queue-health ownership semantics.
- **Kill/defer criteria**: Stop if leased queue depth is intentionally allowed for fact or read-model tables, if validation only checks docs, or if the fix touches worker runtime behavior.
- **Eval/repair signal**: queue-depth table masquerading, fact/read-model queue drift, control-plane ownership drift, manifest validation drift, and SDD generated index drift.
- **Implementation**: Add manifest validation rejecting `queue_depth_table` whenever the table is absent from the same manifest's `writes_control_plane`.
- **Verification**: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_queue_depth_tables_outside_control_plane -q`
- **Review owner**: parent
- **Status**: [x]

### Task 137 — Queue health tables are control-plane-owned

- **File(s)**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 136
- **Touch set**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/worker_manifest.py` for queue-health control-plane ownership validation semantics.
- **Failing test first**: `tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_queue_health_tables_outside_control_plane` — patch a manifest to point `queue_health_tables` at an owned read-model table and assert manifest validation raises before facts or read models can masquerade as queue-health surfaces.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Explicit queue-health declarations must be owned through `writes_control_plane`; generic `owned_tables` membership is not sufficient for queue-health harnesses.
- **On-demand context**: `src/parallax/app/runtime/worker_manifest.py`, `tests/architecture/test_worker_inventory_contract.py`, and worker queue-health ownership semantics.
- **Kill/defer criteria**: Stop if queue-health reporting is intentionally allowed for fact or read-model tables, if validation only checks docs, or if the fix touches worker runtime behavior.
- **Eval/repair signal**: queue-health table masquerading, fact/read-model queue-health drift, control-plane ownership drift, manifest validation drift, and SDD generated index drift.
- **Implementation**: Add manifest validation rejecting `queue_health_tables` values absent from the same manifest's `writes_control_plane`.
- **Verification**: `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_queue_health_tables_outside_control_plane -q`
- **Review owner**: parent
- **Status**: [x]

### Task 138 — Publisher changed rows require identity columns before hashing

- **File(s)**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 137
- **Touch set**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/current_read_model_publisher.py` for changed-row identity validation order semantics.
- **Failing test first**: `tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_missing_identity_column_before_payload_hashing` — call `changed_rows()` with a row missing a stable identity column and assert publisher validation raises a dedicated missing-identity error before explicit payload hashing can raise `KeyError`.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: every `CurrentReadModelPublisher.identity_columns` entry must be present in each changed row before payload hashing, existing-hash lookup, or changed-row write preparation consumes row data as stable serving truth.
- **On-demand context**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, and stable current read-model publisher contracts.
- **Kill/defer criteria**: Stop if missing identity columns intentionally fall through as payload errors, if validation only checks caller code, or if the fix touches projection worker runtime behavior.
- **Eval/repair signal**: missing stable identity columns, payload hashing masking identity drift, changed-row write drift, publisher validation drift, and SDD generated index drift.
- **Implementation**: Add row identity validation for missing identity columns and call `row_identity()` before `row_payload_hash()` inside `changed_rows()`.
- **Verification**: `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_missing_identity_column_before_payload_hashing -q`
- **Review owner**: parent
- **Status**: [x]

### Task 139 — Publisher changed-row batches reject duplicate identities

- **File(s)**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 138
- **Touch set**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/current_read_model_publisher.py` for changed-row batch identity uniqueness semantics.
- **Failing test first**: `tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_duplicate_row_identities_in_batch` — call `changed_rows()` with two rows sharing one stable identity tuple and assert publisher validation raises before preparing duplicate writes for one current read-model row.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: each `CurrentReadModelPublisher.changed_rows()` batch must contain at most one row per stable identity tuple before row payload hashing or changed-row write preparation consumes rows as compact current-serving truth.
- **On-demand context**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, and stable current read-model publisher contracts.
- **Kill/defer criteria**: Stop if duplicate identity rows are intentionally accepted as last-write-wins semantics, if validation only checks caller code, or if the fix touches projection worker runtime behavior.
- **Eval/repair signal**: duplicate stable row identities, ambiguous current-row writes, write amplification drift, publisher validation drift, and SDD generated index drift.
- **Implementation**: Track seen identity tuples inside `changed_rows()` and raise as soon as a batch repeats one stable current-row identity.
- **Verification**: `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_duplicate_row_identities_in_batch -q`
- **Review owner**: parent
- **Status**: [x]

### Task 140 — Publisher missing payload columns use dedicated row-shape errors

- **File(s)**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 139
- **Touch set**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/current_read_model_publisher.py` for explicit payload row-shape validation semantics.
- **Failing test first**: `tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_missing_explicit_payload_column` — tighten the existing missing explicit payload column test to require a dedicated `current read model row missing payload columns` error instead of raw `KeyError`.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: missing explicit `CurrentReadModelPublisher.payload_columns` entries must fail with a publisher row-shape validation error before row payload hashes become harness evidence.
- **On-demand context**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, and stable current read-model publisher contracts.
- **Kill/defer criteria**: Stop if raw `KeyError` is intentionally part of the publisher API, if validation only checks caller code, or if the fix touches projection worker runtime behavior.
- **Eval/repair signal**: missing explicit payload columns, opaque mapping errors, row-shape validation drift, publisher validation drift, and SDD generated index drift.
- **Implementation**: Add explicit payload-column presence validation inside `row_payload_hash()` before building the payload dict.
- **Verification**: `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_missing_explicit_payload_column -q`
- **Review owner**: parent
- **Status**: [x]

### Task 141 — Publisher changed rows reject non-string row columns

- **File(s)**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 140
- **Touch set**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/current_read_model_publisher.py` for changed-row row-column validation semantics.
- **Failing test first**: `tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_non_string_row_columns_before_write_preparation` — call `changed_rows()` with a row containing a non-string key and assert publisher validation raises before write preparation.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: current read-model changed-row inputs must have string top-level row columns before payload hashing, stable identity reads, or serving-row write preparation can consume them.
- **On-demand context**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, and current read-model row-shape contracts.
- **Kill/defer criteria**: Stop if non-string mapping keys are an intentional publisher API, if validation belongs only in database adapters, or if the fix requires projection worker runtime rewrites.
- **Eval/repair signal**: non-string row keys, compatibility-shaped mapping payloads, row-column validation drift, publisher changed-row write preparation drift, and SDD generated index drift.
- **Implementation**: Add top-level row-column validation before `row_identity()` and `row_payload_hash()` consume a row.
- **Verification**: `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_non_string_row_columns_before_write_preparation -q`
- **Review owner**: parent
- **Status**: [x]

### Task 142 — Publisher changed rows reject null identity values

- **File(s)**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 141
- **Touch set**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/current_read_model_publisher.py` for changed-row identity-value validation semantics.
- **Failing test first**: `tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_null_row_identity_values_before_hashing` — call `changed_rows()` with a row whose stable identity value is `None` and assert publisher validation raises before payload hashing or write preparation.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: current read-model changed-row identities must resolve to non-null product/window values before payload hashing, existing-hash lookup, duplicate identity checks, or serving-row write preparation consume them.
- **On-demand context**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, and current read-model stable identity contracts.
- **Kill/defer criteria**: Stop if nullable current-row identity values are an intentional serving contract, if validation belongs only in concrete projection SQL, or if the fix requires changing existing read-model schemas.
- **Eval/repair signal**: null current-row identity values, absent product/window keys, stable identity validation drift, publisher changed-row write preparation drift, and SDD generated index drift.
- **Implementation**: Add null identity-value validation inside `row_identity()` after missing-column checks and before returning the identity tuple.
- **Verification**: `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_null_row_identity_values_before_hashing -q`
- **Review owner**: parent
- **Status**: [x]

### Task 143 — Publisher changed rows reject blank identity values

- **File(s)**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 142
- **Touch set**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/current_read_model_publisher.py` for changed-row identity-value validation semantics.
- **Failing test first**: `tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_blank_row_identity_values_before_hashing` — call `changed_rows()` with a row whose stable identity value is a blank string and assert publisher validation raises before payload hashing or write preparation.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: current read-model changed-row string identities must be non-blank product/window values before payload hashing, existing-hash lookup, duplicate identity checks, or serving-row write preparation consume them.
- **On-demand context**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, and current read-model stable identity contracts.
- **Kill/defer criteria**: Stop if blank current-row identity values are an intentional serving contract, if validation belongs only in concrete projection SQL, or if the fix requires changing existing read-model schemas.
- **Eval/repair signal**: blank current-row identity values, whitespace product/window placeholders, stable identity validation drift, publisher changed-row write preparation drift, and SDD generated index drift.
- **Implementation**: Add blank string identity-value validation inside `row_identity()` after null identity checks and before returning the identity tuple.
- **Verification**: `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_blank_row_identity_values_before_hashing -q`
- **Review owner**: parent
- **Status**: [x]

### Task 144 — Publisher identity columns reject list-shaped declarations

- **File(s)**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 143
- **Touch set**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/current_read_model_publisher.py` for publisher identity-column declaration shape validation semantics.
- **Failing test first**: `tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_non_tuple_identity_columns` — construct `CurrentReadModelPublisher` with list-shaped stable identity columns and assert publisher construction raises before downstream identity validation consumes it.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `CurrentReadModelPublisher.identity_columns` must be a tuple before blank, duplicate, lifecycle, row-identity, payload-hash, or changed-row checks can consume it as source truth.
- **On-demand context**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, and tuple-valued current read-model identity contracts.
- **Kill/defer criteria**: Stop if list-shaped publisher identity declarations are an intentional API, if validation only belongs in worker manifests, or if the fix requires compatibility coercion.
- **Eval/repair signal**: list-shaped publisher identity columns, compatibility-shaped serving identity declarations, publisher construction validation drift, and SDD generated index drift.
- **Implementation**: Add publisher construction validation rejecting non-tuple `identity_columns` before empty, string, blank, duplicate, or lifecycle checks.
- **Verification**: `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_non_tuple_identity_columns -q`
- **Review owner**: parent
- **Status**: [x]

### Task 145 — Publisher changed rows reject non-mapping row containers

- **File(s)**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 144
- **Touch set**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/current_read_model_publisher.py` for changed-row row-shape validation semantics.
- **Failing test first**: `tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_non_mapping_rows_before_column_validation` — call `changed_rows()` with a list-shaped row and assert publisher validation raises a dedicated mapping error before row-column validation.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: each `CurrentReadModelPublisher.changed_rows()` row must be a mapping before column, stable identity, payload hash, existing-hash, duplicate identity, or write-preparation checks can consume it.
- **On-demand context**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, and current read-model changed-row shape contracts.
- **Kill/defer criteria**: Stop if list-shaped changed rows are an intentional API, if validation only belongs in concrete repositories, or if the fix requires compatibility coercion.
- **Eval/repair signal**: list-shaped changed rows, row container compatibility drift, row-column validation masking, publisher changed-row write preparation drift, and SDD generated index drift.
- **Implementation**: Add row mapping validation before row-column validation inside the publisher row-shape guard.
- **Verification**: `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_non_mapping_rows_before_column_validation -q`
- **Review owner**: parent
- **Status**: [x]

### Task 146 — Publisher changed rows reject non-mapping existing hashes

- **File(s)**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 145
- **Touch set**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/current_read_model_publisher.py` for changed-row existing-hash validation semantics.
- **Failing test first**: `tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_non_mapping_existing_hashes_before_hash_lookup` — call `changed_rows()` with list-shaped `existing_hashes` and assert publisher validation raises a dedicated mapping error before hash lookup.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `CurrentReadModelPublisher.changed_rows()` existing-hash state must be a mapping from stable identity tuples to payload hashes before row validation, payload hashing, hash lookup, duplicate identity, unchanged-row skip, or write-preparation checks can consume it.
- **On-demand context**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, and current read-model unchanged-row idempotency contracts.
- **Kill/defer criteria**: Stop if list-shaped existing-hash indexes are an intentional API, if validation only belongs in concrete projection repositories, or if the fix requires compatibility coercion.
- **Eval/repair signal**: list-shaped existing hash indexes, unchanged-row idempotency drift, opaque hash lookup errors, publisher changed-row write preparation drift, and SDD generated index drift.
- **Implementation**: Add `existing_hashes` mapping validation at the start of `changed_rows()` before iterating rows or looking up payload hashes.
- **Verification**: `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_non_mapping_existing_hashes_before_hash_lookup -q`
- **Review owner**: parent
- **Status**: [x]

### Task 147 — Publisher changed rows reject non-tuple existing-hash identities

- **File(s)**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 146
- **Touch set**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/current_read_model_publisher.py` for changed-row existing-hash identity validation semantics.
- **Failing test first**: `tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_non_tuple_existing_hash_identity_keys_before_hash_lookup` — call `changed_rows()` with string-shaped `existing_hashes` keys and assert publisher validation raises before unchanged-row lookup silently misses the stable identity tuple.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: each `CurrentReadModelPublisher.changed_rows()` existing-hash identity key must be a tuple before row validation, payload hashing, hash lookup, unchanged-row skip, duplicate identity checks, or write-preparation can consume it.
- **On-demand context**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, and current read-model unchanged-row idempotency contracts.
- **Kill/defer criteria**: Stop if string-shaped existing-hash identity keys are an intentional API, if validation only belongs in concrete projection repositories, or if the fix requires compatibility coercion.
- **Eval/repair signal**: string existing hash identity keys, unchanged-row write amplification, stable identity lookup drift, publisher changed-row write preparation drift, and SDD generated index drift.
- **Implementation**: Validate existing-hash identity keys are tuples at the start of `changed_rows()` before iterating rows or looking up payload hashes.
- **Verification**: `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_non_tuple_existing_hash_identity_keys_before_hash_lookup -q`
- **Review owner**: parent
- **Status**: [x]

### Task 148 — Publisher changed rows reject wrong-arity existing-hash identities

- **File(s)**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 147
- **Touch set**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/current_read_model_publisher.py` for changed-row existing-hash identity arity validation semantics.
- **Failing test first**: `tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_wrong_arity_existing_hash_identity_keys_before_hash_lookup` — call `changed_rows()` with a tuple-shaped `existing_hashes` key whose arity differs from `identity_columns` and assert publisher validation raises before unchanged-row lookup silently misses the stable identity tuple.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: each `CurrentReadModelPublisher.changed_rows()` existing-hash identity tuple must have the same arity as `identity_columns` before row validation, payload hashing, hash lookup, unchanged-row skip, duplicate identity checks, or write-preparation can consume it.
- **On-demand context**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, and current read-model unchanged-row idempotency contracts.
- **Kill/defer criteria**: Stop if wrong-arity existing-hash identity tuples are an intentional API, if validation only belongs in concrete projection repositories, or if the fix requires compatibility coercion.
- **Eval/repair signal**: wrong-arity existing hash identity keys, unchanged-row write amplification, stable identity lookup drift, publisher changed-row write preparation drift, and SDD generated index drift.
- **Implementation**: Validate existing-hash identity tuple arity matches `identity_columns` at the start of `changed_rows()` before iterating rows or looking up payload hashes.
- **Verification**: `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_wrong_arity_existing_hash_identity_keys_before_hash_lookup -q`
- **Review owner**: parent
- **Status**: [x]

### Task 149 — Publisher changed rows reject non-string existing-hash values

- **File(s)**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 148
- **Touch set**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/current_read_model_publisher.py` for changed-row existing-hash value validation semantics.
- **Failing test first**: `tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_non_string_existing_hash_values_before_hash_lookup` — call `changed_rows()` with a numeric `existing_hashes` value and assert publisher validation raises before unchanged-row lookup silently misses the stable hash.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: each `CurrentReadModelPublisher.changed_rows()` existing-hash value must be a string payload hash or `None` before row validation, payload hashing, hash lookup, unchanged-row skip, duplicate identity checks, or write-preparation can consume it.
- **On-demand context**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, and current read-model unchanged-row idempotency contracts.
- **Kill/defer criteria**: Stop if numeric or object existing-hash values are an intentional API, if validation only belongs in concrete projection repositories, or if the fix requires compatibility coercion.
- **Eval/repair signal**: non-string existing hash values, unchanged-row write amplification, stable payload hash lookup drift, publisher changed-row write preparation drift, and SDD generated index drift.
- **Implementation**: Validate existing-hash values are strings or `None` at the start of `changed_rows()` before iterating rows or looking up payload hashes.
- **Verification**: `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_non_string_existing_hash_values_before_hash_lookup -q`
- **Review owner**: parent
- **Status**: [x]

### Task 150 — Publisher changed rows reject malformed existing-hash strings

- **File(s)**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 149
- **Touch set**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/current_read_model_publisher.py` for changed-row existing-hash value-format validation semantics.
- **Failing test first**: `tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_malformed_existing_hash_values_before_hash_lookup` — call `changed_rows()` with a malformed string `existing_hashes` value and assert publisher validation raises before unchanged-row lookup silently misses the stable hash.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: each non-null `CurrentReadModelPublisher.changed_rows()` existing-hash value must be a canonical `sha256:` plus 64 lowercase hex payload hash before row validation, payload hashing, hash lookup, unchanged-row skip, duplicate identity checks, or write-preparation can consume it.
- **On-demand context**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, and current read-model unchanged-row idempotency contracts.
- **Kill/defer criteria**: Stop if malformed existing-hash strings are an intentional API, if validation only belongs in concrete projection repositories, or if the fix requires compatibility coercion.
- **Eval/repair signal**: malformed existing hash strings, unchanged-row write amplification, stable payload hash lookup drift, publisher changed-row write preparation drift, and SDD generated index drift.
- **Implementation**: Validate existing-hash string values are canonical payload hashes at the start of `changed_rows()` before iterating rows or looking up payload hashes.
- **Verification**: `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_malformed_existing_hash_values_before_hash_lookup -q`
- **Review owner**: parent
- **Status**: [x]

### Task 151 — Publisher changed rows reject malformed row batches

- **File(s)**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 150
- **Touch set**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/current_read_model_publisher.py` for changed-row batch-shape validation semantics.
- **Failing test first**: `tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_non_sequence_row_batches_before_row_validation` — call `changed_rows()` with scalar, mapping-shaped, and string-shaped `rows` values and assert publisher validation raises before row validation splits compatibility containers into fake row values.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `CurrentReadModelPublisher.changed_rows()` row batches must be non-string sequences before row validation, column validation, stable identity extraction, payload hashing, duplicate identity checks, or changed-row write preparation can consume the container.
- **On-demand context**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, and current read-model changed-row batch shape contracts.
- **Kill/defer criteria**: Stop if scalar, mapping-shaped, or string-shaped row batches are an intentional API, if validation only belongs in concrete projection repositories, or if the fix requires compatibility coercion.
- **Eval/repair signal**: malformed row batches, scalar row-container `TypeError`, mapping/string batch iteration drift, row validation masking, publisher changed-row write preparation drift, and SDD generated index drift.
- **Implementation**: Add changed-row batch validation before row iteration so scalar, mapping-shaped, and string-shaped batches raise a dedicated row-batch validation error.
- **Verification**: `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_non_sequence_row_batches_before_row_validation -q`
- **Review owner**: parent
- **Status**: [x]

### Task 152 — Stable payload hash rejects malformed payload containers

- **File(s)**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 151
- **Touch set**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/current_read_model_publisher.py` for stable payload hash input-shape validation semantics.
- **Failing test first**: `tests/architecture/test_worker_manifest_static_contracts.py::test_stable_current_payload_hash_rejects_non_mapping_payloads` — call `stable_current_payload_hash()` with scalar, list-of-pairs-shaped, and string-shaped payload values and assert hash validation raises before `dict(...)` coercion can preserve compatibility containers.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `stable_current_payload_hash()` payload input must be a mapping before JSON normalization or hash generation can consume it as current read-model serving payload truth.
- **On-demand context**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, and current read-model payload hash idempotency contracts.
- **Kill/defer criteria**: Stop if list-of-pairs or scalar payload hash inputs are an intentional API, if validation only belongs in caller-specific publishers, or if the fix requires compatibility coercion.
- **Eval/repair signal**: malformed payload containers, `dict(...)` coercion drift, list-of-pairs payload compatibility, stable payload hash idempotency drift, and SDD generated index drift.
- **Implementation**: Add stable payload hash input validation before `dict(payload)`, JSON normalization, or hash generation.
- **Verification**: `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_stable_current_payload_hash_rejects_non_mapping_payloads -q`
- **Review owner**: parent
- **Status**: [x]

### Task 153 — Stable payload hash rejects non-string payload keys

- **File(s)**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 152
- **Touch set**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/current_read_model_publisher.py` for stable payload hash key validation semantics.
- **Failing test first**: `tests/architecture/test_worker_manifest_static_contracts.py::test_stable_current_payload_hash_rejects_non_string_payload_keys` — call `stable_current_payload_hash()` with a mapping payload containing a numeric key and assert hash validation raises before JSON normalization can stringify compatibility-shaped mapping keys.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `stable_current_payload_hash()` top-level payload keys must be strict strings before `_json_ready()`, JSON normalization, or hash generation can consume them as current read-model payload truth.
- **On-demand context**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, and current read-model payload hash idempotency contracts.
- **Kill/defer criteria**: Stop if numeric payload keys are an intentional direct hash-helper API, if validation only belongs in row-level publishers, or if the fix requires compatibility key coercion.
- **Eval/repair signal**: non-string payload keys, JSON normalization key stringification, stable payload hash idempotency drift, compatibility-shaped mapping keys, and SDD generated index drift.
- **Implementation**: Add stable payload hash key validation before `_json_ready()`, JSON normalization, or hash generation.
- **Verification**: `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_stable_current_payload_hash_rejects_non_string_payload_keys -q`
- **Review owner**: parent
- **Status**: [x]

### Task 154 — Stable payload hash rejects nested non-string payload keys

- **File(s)**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 153
- **Touch set**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/current_read_model_publisher.py` for recursive stable payload hash key validation semantics.
- **Failing test first**: `tests/architecture/test_worker_manifest_static_contracts.py::test_stable_current_payload_hash_rejects_nested_non_string_payload_keys` — call `stable_current_payload_hash()` with a factor snapshot containing a nested numeric key and assert hash validation raises before JSON normalization can stringify compatibility-shaped nested mapping keys.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: every mapping key reachable inside a `stable_current_payload_hash()` payload must be a strict string before `_json_ready()`, JSON normalization, or hash generation can consume nested JSON payload blocks as current read-model payload truth.
- **On-demand context**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, and current read-model payload hash idempotency contracts.
- **Kill/defer criteria**: Stop if nested numeric payload keys are an intentional direct hash-helper API, if validation only belongs in concrete row publishers, or if the fix requires compatibility key coercion.
- **Eval/repair signal**: nested non-string payload keys, factor snapshot key stringification, JSON normalization compatibility drift, stable payload hash idempotency drift, and SDD generated index drift.
- **Implementation**: Replace top-level-only stable payload key validation with recursive payload key validation before `_json_ready()`, and remove `_json_ready()` mapping-key string coercion.
- **Verification**: `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_stable_current_payload_hash_rejects_nested_non_string_payload_keys -q`
- **Review owner**: parent
- **Status**: [x]

### Task 155 — Stable payload hash rejects generic isoformat payload values

- **File(s)**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 154
- **Touch set**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/current_read_model_publisher.py` for stable payload hash value validation semantics.
- **Failing test first**: `tests/architecture/test_worker_manifest_static_contracts.py::test_stable_current_payload_hash_rejects_generic_isoformat_payload_values` — call `stable_current_payload_hash()` with an arbitrary object exposing `isoformat()` and assert hash validation raises before generic ISO formatting can preserve compatibility-shaped payload values.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `stable_current_payload_hash()` payload values must be JSON-compatible scalars, `Decimal`, real date/time values, or supported containers before `_json_ready()`, JSON normalization, or hash generation can consume them as current read-model payload truth.
- **On-demand context**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, and current read-model payload hash idempotency contracts.
- **Kill/defer criteria**: Stop if arbitrary `isoformat()` objects are an intentional direct hash-helper API, if validation only belongs in concrete row publishers, or if the fix requires generic object coercion.
- **Eval/repair signal**: generic `isoformat()` payload values, unsupported payload object coercion, stable payload hash idempotency drift, JSON normalization compatibility drift, and SDD generated index drift.
- **Implementation**: Add recursive stable payload value validation before `_json_ready()`, restrict ISO formatting to real date/time values, and remove generic `hasattr(value, "isoformat")` coercion.
- **Verification**: `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_stable_current_payload_hash_rejects_generic_isoformat_payload_values -q`
- **Review owner**: parent
- **Status**: [x]

### Task 156 — Stable payload hash rejects non-finite payload numbers

- **File(s)**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 155
- **Touch set**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/current_read_model_publisher.py` for stable payload hash numeric-value validation semantics.
- **Failing test first**: `tests/architecture/test_worker_manifest_static_contracts.py::test_stable_current_payload_hash_rejects_non_finite_payload_numbers` — call `stable_current_payload_hash()` with float and Decimal NaN/Infinity values and assert hash validation raises before JSON serialization or Decimal stringification can consume non-finite payload numbers.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `stable_current_payload_hash()` payload numeric values must be finite before `_json_ready()`, JSON serialization, Decimal stringification, or hash generation can consume them as current read-model payload truth.
- **On-demand context**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, and current read-model payload hash idempotency contracts.
- **Kill/defer criteria**: Stop if non-finite values are an intentional current read-model serving payload contract, if validation only belongs in concrete row publishers, or if the fix requires serializer-dependent error handling.
- **Eval/repair signal**: float NaN/Infinity JSON errors, Decimal NaN/Infinity stringification, stable payload hash idempotency drift, JSON normalization compatibility drift, and SDD generated index drift.
- **Implementation**: Add recursive stable payload numeric validation before `_json_ready()` and reject non-finite float and Decimal values with a dedicated payload-number validation error.
- **Verification**: `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_stable_current_payload_hash_rejects_non_finite_payload_numbers -q`
- **Review owner**: parent
- **Status**: [x]

### Task 157 — Stable payload hash rejects unordered payload containers

- **File(s)**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 156
- **Touch set**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/current_read_model_publisher.py` for stable payload hash container validation semantics.
- **Failing test first**: `tests/architecture/test_worker_manifest_static_contracts.py::test_stable_current_payload_hash_rejects_unordered_payload_containers` — call `stable_current_payload_hash()` with set and frozenset payload values and assert hash validation raises before JSON normalization can sort unordered compatibility containers into serving hashes.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `stable_current_payload_hash()` payload containers must be mapping, list, or tuple traversal shapes before `_json_ready()`, JSON normalization, or hash generation can consume them as current read-model payload truth; unordered set/frozenset values are rejected instead of sorted.
- **On-demand context**: `src/parallax/app/runtime/current_read_model_publisher.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, and current read-model payload hash idempotency contracts.
- **Kill/defer criteria**: Stop if unordered set/frozenset payload values are an intentional serving payload contract, if validation only belongs in concrete row publishers, or if the fix requires retaining set sorting in `_json_ready()`.
- **Eval/repair signal**: unordered payload containers, set/frozenset sorting, stable payload hash idempotency drift, JSON normalization compatibility drift, and SDD generated index drift.
- **Implementation**: Reject set and frozenset payload values during recursive payload validation, stop traversing them as key containers, and remove `_json_ready()` set/frozenset sorting.
- **Verification**: `uv run pytest tests/architecture/test_worker_manifest_static_contracts.py::test_stable_current_payload_hash_rejects_unordered_payload_containers -q`
- **Review owner**: parent
- **Status**: [x]

### Task 158 — CEX board hash uses shared current payload contract

- **File(s)**: `src/parallax/domains/cex_market_intel/repositories/cex_oi_radar_repository.py`, `tests/unit/domains/cex_market_intel/test_cex_oi_radar_repository.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 157
- **Touch set**: `src/parallax/domains/cex_market_intel/repositories/cex_oi_radar_repository.py`, `tests/unit/domains/cex_market_intel/test_cex_oi_radar_repository.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/domains/cex_market_intel/repositories/cex_oi_radar_repository.py` for CEX board publication payload hash semantics and current-row idempotency.
- **Failing test first**: `tests/unit/domains/cex_market_intel/test_cex_oi_radar_repository.py::test_board_payload_hash_rejects_legacy_score_component_keys` — call `_board_payload_hash()` with a row whose `score_components` mapping has a non-string key and assert the shared current payload-key validation raises before local key stringification can preserve compatibility-shaped score component payloads.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: CEX board publication hashing must use `stable_current_payload_hash()` from `src/parallax/platform/current_read_model_payload_hash.py`; the domain repository must not keep a local payload hash normalizer that stringifies mapping keys, sorts unordered containers, or accepts arbitrary `isoformat()` payload values.
- **On-demand context**: `src/parallax/domains/cex_market_intel/ARCHITECTURE.md`, `src/parallax/domains/cex_market_intel/repositories/cex_oi_radar_repository.py`, `tests/unit/domains/cex_market_intel/test_cex_oi_radar_repository.py`, and current read-model payload hash idempotency contracts.
- **Kill/defer criteria**: Stop if CEX board hashes intentionally require domain-local compatibility normalization, if existing production rows must be backfilled before strict hash validation, or if the shared hash helper cannot preserve unchanged hashes for compliant board payloads.
- **Eval/repair signal**: local `_stable_current_payload_hash()`, local `_json_ready()`, score component key stringification, set/frozenset sorting, generic `isoformat()` payload values, CEX board idempotency drift, and SDD generated index drift.
- **Implementation**: Import and use `stable_current_payload_hash()` inside `_board_payload_hash()`, remove the local CEX `_stable_current_payload_hash()` and `_json_ready()` compatibility normalizers, and keep existing board unchanged-payload tests green for compliant payloads.
- **Verification**: `uv run pytest tests/unit/domains/cex_market_intel/test_cex_oi_radar_repository.py::test_board_payload_hash_rejects_legacy_score_component_keys -q`
- **Review owner**: parent
- **Status**: [x]

### Task 159 — Runtime package init avoids scheduler side effects

- **File(s)**: `src/parallax/app/runtime/__init__.py`, `tests/unit/domains/cex_market_intel/test_cex_oi_radar_board_worker.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 158
- **Touch set**: `src/parallax/app/runtime/__init__.py`, `tests/unit/domains/cex_market_intel/test_cex_oi_radar_board_worker.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/__init__.py` for runtime package export and import side-effect semantics.
- **Failing test first**: `tests/unit/domains/cex_market_intel/test_cex_oi_radar_board_worker.py::test_cex_oi_radar_board_worker_publishes_current_board` — after CEX board hashing imports the shared runtime payload hash helper, importing the CEX worker module failed during collection before this test could run because `parallax.app.runtime.__init__` imported `WorkerScheduler`, which imported `worker_manifest` and validated manifests before `CexOiRadarBoardWorker` was fully importable.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: importing a shared runtime helper from a domain repository must not trigger scheduler import, `worker_manifest` validation, worker class imports, or clean-process manifest side effects through package initialization.
- **On-demand context**: `src/parallax/app/runtime/__init__.py`, `src/parallax/app/runtime/worker_scheduler.py`, `src/parallax/app/runtime/worker_manifest.py`, and `tests/unit/domains/cex_market_intel/test_cex_oi_radar_board_worker.py`.
- **Kill/defer criteria**: Stop if `WorkerScheduler` is a supported package-root export with live consumers, if removing the re-export breaks explicit runtime import contracts, or if the fix requires lazy compatibility shims instead of explicit module imports.
- **Eval/repair signal**: CEX worker import collection failure, package-root scheduler re-export, manifest validation during helper import, worker class import cycle, and SDD generated index drift.
- **Implementation**: Remove the `WorkerScheduler` re-export from `parallax.app.runtime.__init__` and keep scheduler consumers on explicit `parallax.app.runtime.worker_scheduler` imports.
- **Verification**: `uv run pytest tests/unit/domains/cex_market_intel/test_cex_oi_radar_board_worker.py -q`
- **Review owner**: parent
- **Status**: [x]

### Task 160 — CEX detail hash uses shared current payload contract

- **File(s)**: `src/parallax/domains/cex_market_intel/repositories/cex_detail_snapshot_repository.py`, `tests/unit/domains/cex_market_intel/test_cex_detail_snapshot_repository.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 159
- **Touch set**: `src/parallax/domains/cex_market_intel/repositories/cex_detail_snapshot_repository.py`, `tests/unit/domains/cex_market_intel/test_cex_detail_snapshot_repository.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/domains/cex_market_intel/repositories/cex_detail_snapshot_repository.py` for CEX detail snapshot payload hash semantics and current-row idempotency.
- **Failing test first**: `tests/unit/domains/cex_market_intel/test_cex_detail_snapshot_repository.py::test_detail_payload_hash_rejects_legacy_level_band_keys` — call `_detail_payload_hash()` with a `level_bands` mapping that has a non-string key and assert the shared current payload-key validation raises before local key stringification or historical migration-golden numeric canonicalization can preserve compatibility-shaped level-band payloads.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: CEX detail snapshot hashing must use `stable_current_payload_hash()` from `src/parallax/platform/current_read_model_payload_hash.py`; the repository must not keep local generic payload hash or JSON normalizer functions that stringify mapping keys, sort unordered containers, accept arbitrary `isoformat()` values, or force runtime hashes to match historical migration-golden numeric compatibility.
- **On-demand context**: `src/parallax/domains/cex_market_intel/ARCHITECTURE.md`, `src/parallax/domains/cex_market_intel/repositories/cex_detail_snapshot_repository.py`, `tests/unit/domains/cex_market_intel/test_cex_detail_snapshot_repository.py`, and current read-model payload hash idempotency contracts.
- **Kill/defer criteria**: Stop if CEX detail hashes intentionally require domain-local compatibility normalization, if existing production rows must be backfilled before strict hash validation, or if the shared hash helper cannot preserve unchanged hashes for compliant detail payloads.
- **Eval/repair signal**: local `_stable_payload_hash()`, local `_json_ready()`, level-band key stringification, set/frozenset sorting, generic `isoformat()` payload values, migration-golden numeric canonicalization coupling, CEX detail idempotency drift, and SDD generated index drift.
- **Implementation**: Import and use `stable_current_payload_hash()` inside `_detail_payload_hash()`, remove local CEX detail `_stable_payload_hash()`, `_json_ready()`, and generic numeric canonicalizer compatibility, and update overfitted migration-golden tests to assert current product timestamp behavior without preserving the historical hash algorithm.
- **Verification**: `uv run pytest tests/unit/domains/cex_market_intel/test_cex_detail_snapshot_repository.py::test_detail_payload_hash_rejects_legacy_level_band_keys -q`
- **Review owner**: parent
- **Status**: [x]

### Task 161 — CEX detail source refs reject legacy keys before filtering

- **File(s)**: `src/parallax/domains/cex_market_intel/repositories/cex_detail_snapshot_repository.py`, `tests/unit/domains/cex_market_intel/test_cex_detail_snapshot_repository.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 160
- **Touch set**: `src/parallax/domains/cex_market_intel/repositories/cex_detail_snapshot_repository.py`, `tests/unit/domains/cex_market_intel/test_cex_detail_snapshot_repository.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/domains/cex_market_intel/repositories/cex_detail_snapshot_repository.py` for CEX detail source-ref filtering and payload hash key validation semantics.
- **Failing test first**: `tests/unit/domains/cex_market_intel/test_cex_detail_snapshot_repository.py::test_detail_payload_hash_rejects_legacy_source_ref_keys` — call `_detail_payload_hash()` with a `source_refs` mapping that has a non-string key and assert the shared current payload-key validation raises before source-ref metadata filtering can stringify compatibility-shaped payload keys.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: source-ref metadata filtering must require strict string keys before filtering `_HASH_METADATA_FIELDS`; it must not call `str(key)` to preserve legacy source-ref payload shapes.
- **On-demand context**: `src/parallax/domains/cex_market_intel/ARCHITECTURE.md`, `src/parallax/domains/cex_market_intel/repositories/cex_detail_snapshot_repository.py`, `tests/unit/domains/cex_market_intel/test_cex_detail_snapshot_repository.py`, and current read-model payload hash idempotency contracts.
- **Kill/defer criteria**: Stop if non-string source-ref keys are an intentional CEX detail read-model contract, if the source-ref filtering layer must accept legacy JSON-ish shapes, or if rejecting them breaks compliant builder output.
- **Eval/repair signal**: source-ref key stringification, metadata filtering before validation, CEX detail payload hash idempotency drift, and SDD generated index drift.
- **Implementation**: Validate source-ref mapping keys as strict strings before metadata filtering and raise the same current payload hash non-string-key error for legacy source-ref keys.
- **Verification**: `uv run pytest tests/unit/domains/cex_market_intel/test_cex_detail_snapshot_repository.py::test_detail_payload_hash_rejects_legacy_source_ref_keys -q`
- **Review owner**: parent
- **Status**: [x]

### Task 162 — Token profile current hash uses shared current payload contract

- **File(s)**: `src/parallax/domains/asset_market/repositories/token_profile_current_repository.py`, `tests/unit/domains/asset_market/test_token_profile_current_repository.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 161
- **Touch set**: `src/parallax/domains/asset_market/repositories/token_profile_current_repository.py`, `tests/unit/domains/asset_market/test_token_profile_current_repository.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/domains/asset_market/repositories/token_profile_current_repository.py` for token profile current payload hash semantics and current-row idempotency.
- **Failing test first**: `tests/unit/domains/asset_market/test_token_profile_current_repository.py::test_token_profile_current_payload_hash_rejects_legacy_source_payload_keys` — call `TokenProfileCurrentRepository.upsert_current()` with `source_payload_json` containing a non-string key and assert the shared current payload-key validation raises before `postgres_safe_json()` can stringify compatibility-shaped source payload keys.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: token profile current row hashing must use `stable_current_payload_hash()` from `src/parallax/platform/current_read_model_payload_hash.py`; JSON payload blocks must be validated before DB JSON sanitation so `source_payload_json` and other nested current payload values cannot preserve legacy non-string keys through key stringification.
- **On-demand context**: `src/parallax/domains/asset_market/ARCHITECTURE.md`, `src/parallax/domains/asset_market/repositories/token_profile_current_repository.py`, `tests/unit/domains/asset_market/test_token_profile_current_repository.py`, and current read-model payload hash idempotency contracts.
- **Kill/defer criteria**: Stop if token profile current intentionally supports non-string JSON payload keys, if production source payload rows require compatibility key stringification at runtime, or if the shared hash helper cannot preserve unchanged hashes for compliant profile payloads.
- **Eval/repair signal**: local `_stable_payload_hash()`, local `_stable_json_value()`, `postgres_safe_json()` key stringification before validation, profile current idempotency drift, and SDD generated index drift.
- **Implementation**: Validate JSON payload blocks with the shared current payload contract before sanitation, compute `token_profile_current.payload_hash` with `stable_current_payload_hash()`, and delete the repository-local stable payload hash and JSON value normalizers.
- **Verification**: `uv run pytest tests/unit/domains/asset_market/test_token_profile_current_repository.py::test_token_profile_current_payload_hash_rejects_legacy_source_payload_keys -q`
- **Review owner**: parent
- **Status**: [x]

### Task 163 — News source-quality hash uses shared current payload contract

- **File(s)**: `src/parallax/domains/news_intel/repositories/news_repository.py`, `tests/unit/domains/news_intel/test_source_quality_projection.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 162
- **Touch set**: `src/parallax/domains/news_intel/repositories/news_repository.py`, `tests/unit/domains/news_intel/test_source_quality_projection.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/domains/news_intel/repositories/news_repository.py` for News source-quality current-row payload hash semantics and idempotent writes.
- **Failing test first**: `tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_quality_payload_hash_rejects_legacy_diagnostics_keys` — call `NewsRepository.replace_source_quality_rows()` with `diagnostics_json` containing a non-string key and assert the shared current payload-key validation raises before the retired local normalizer can stringify compatibility-shaped diagnostics payload keys.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: News source-quality row hashing must use `stable_current_payload_hash()` from `src/parallax/platform/current_read_model_payload_hash.py`; the repository must not keep a local stable payload hash normalizer that stringifies mapping keys or routes `diagnostics_json` through compatibility sanitation before current payload validation.
- **On-demand context**: `src/parallax/domains/news_intel/ARCHITECTURE.md`, `src/parallax/domains/news_intel/repositories/news_repository.py`, `tests/unit/domains/news_intel/test_source_quality_projection.py`, and current read-model payload hash idempotency contracts.
- **Kill/defer criteria**: Stop if News source-quality intentionally supports non-string diagnostics keys, if production source-quality rows require compatibility key stringification at runtime, or if the shared hash helper cannot preserve unchanged hashes for compliant source-quality payloads.
- **Eval/repair signal**: local `_stable_payload_hash()`, local `_stable_json_value()`, diagnostics key stringification, News source-quality idempotency drift, and SDD generated index drift.
- **Implementation**: Compute `news_source_quality_rows.payload_hash` with `stable_current_payload_hash()`, unwrap `Jsonb` adapter values without stringifying mapping keys, and delete the repository-local stable payload hash and JSON value normalizers.
- **Verification**: `uv run pytest tests/unit/domains/news_intel/test_source_quality_projection.py::test_source_quality_payload_hash_rejects_legacy_diagnostics_keys -q`
- **Review owner**: parent
- **Status**: [x]

### Task 164 — News page-row hash uses shared current payload contract

- **File(s)**: `src/parallax/domains/news_intel/repositories/news_repository.py`, `tests/unit/domains/news_intel/test_news_repository_queries.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 163
- **Touch set**: `src/parallax/domains/news_intel/repositories/news_repository.py`, `tests/unit/domains/news_intel/test_news_repository_queries.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/domains/news_intel/repositories/news_repository.py` for News page-row current-row payload hash semantics and idempotent writes.
- **Failing test first**: `tests/unit/domains/news_intel/test_news_repository_queries.py::test_news_page_row_payload_hash_rejects_legacy_story_keys_before_write` — call `NewsRepository.replace_page_rows_for_items()` with a `story` payload containing a non-string key and assert the shared current payload-key validation raises before serving-row insert can consume compatibility-shaped story keys.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: News page-row hashing must use `stable_current_payload_hash()` from `src/parallax/platform/current_read_model_payload_hash.py`; the repository must not keep a local stable payload hash normalizer that stringifies `story_json`, source, signal, provider-rating, token-impact, market-scope, or agent-admission mapping keys.
- **On-demand context**: `src/parallax/domains/news_intel/ARCHITECTURE.md`, `src/parallax/domains/news_intel/repositories/news_repository.py`, `tests/unit/domains/news_intel/test_news_repository_queries.py`, and current read-model payload hash idempotency contracts.
- **Kill/defer criteria**: Stop if News page rows intentionally support non-string story/payload envelope keys, if production page rows require compatibility key stringification at runtime, or if the shared hash helper cannot preserve unchanged hashes for compliant page payloads.
- **Eval/repair signal**: local `_stable_payload_hash()`, local `_stable_json_value()`, story key stringification, News page-row idempotency drift, and SDD generated index drift.
- **Implementation**: Compute `news_page_rows.payload_hash` with `stable_current_payload_hash()`, unwrap `Jsonb` adapter values without stringifying mapping keys, and assert legacy story-key payloads are rejected before serving-row writes.
- **Verification**: `uv run pytest tests/unit/domains/news_intel/test_news_repository_queries.py::test_news_page_row_payload_hash_rejects_legacy_story_keys_before_write -q`
- **Review owner**: parent
- **Status**: [x]

### Task 165 — Narrative admission hash uses shared current payload contract

- **File(s)**: `src/parallax/domains/narrative_intel/repositories/narrative_repository.py`, `tests/unit/domains/narrative_intel/test_narrative_repository_sql_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 164
- **Touch set**: `src/parallax/domains/narrative_intel/repositories/narrative_repository.py`, `tests/unit/domains/narrative_intel/test_narrative_repository_sql_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/domains/narrative_intel/repositories/narrative_repository.py` for Narrative admission current-row payload hash semantics and idempotent writes.
- **Failing test first**: `tests/unit/domains/narrative_intel/test_narrative_repository_sql_contract.py::test_admission_payload_hash_rejects_legacy_payload_keys` — call `admission_payload_hash()` with a non-string payload key and assert the shared current payload-key validation raises before the retired local normalizer can stringify compatibility-shaped admission payload keys.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Narrative admission row hashing must use `stable_current_payload_hash()` from `src/parallax/platform/current_read_model_payload_hash.py`; the repository must not keep a local stable payload hash normalizer that stringifies mapping keys, sorts unordered containers, or relies on generic `default=str` value conversion.
- **On-demand context**: `src/parallax/domains/narrative_intel/ARCHITECTURE.md`, `src/parallax/domains/narrative_intel/repositories/narrative_repository.py`, `tests/unit/domains/narrative_intel/test_narrative_repository_sql_contract.py`, and current read-model payload hash idempotency contracts.
- **Kill/defer criteria**: Stop if Narrative admissions intentionally support non-string payload keys, if production admissions require compatibility key stringification at runtime, or if the shared hash helper cannot preserve unchanged hashes for compliant admission payloads.
- **Eval/repair signal**: local `_stable_payload_hash()`, local `_json_ready()`, key stringification, unordered-container sorting, generic `default=str` value conversion, Narrative admission idempotency drift, and SDD generated index drift.
- **Implementation**: Compute `narrative_admissions.payload_hash` with `stable_current_payload_hash()`, unwrap `Jsonb` adapter values without stringifying mapping keys, and delete the repository-local stable payload hash and JSON value normalizer.
- **Verification**: `uv run pytest tests/unit/domains/narrative_intel/test_narrative_repository_sql_contract.py::test_admission_payload_hash_rejects_legacy_payload_keys -q`
- **Review owner**: parent
- **Status**: [x]

### Task 166 — Narrative admission hash unwraps only real Jsonb adapters

- **File(s)**: `src/parallax/domains/narrative_intel/repositories/narrative_repository.py`, `tests/unit/domains/narrative_intel/test_narrative_repository_sql_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 165
- **Touch set**: `src/parallax/domains/narrative_intel/repositories/narrative_repository.py`, `tests/unit/domains/narrative_intel/test_narrative_repository_sql_contract.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/domains/narrative_intel/repositories/narrative_repository.py` for Narrative admission payload adapter unwrapping semantics.
- **Failing test first**: `tests/unit/domains/narrative_intel/test_narrative_repository_sql_contract.py::test_admission_payload_hash_rejects_jsonb_like_legacy_adapter_values` — pass an arbitrary object with an `obj` attribute into `admission_payload_hash()` and assert shared current payload validation rejects it instead of generic adapter unwrapping.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Narrative admission hash adapter handling may unwrap only real `psycopg.types.json.Jsonb` values; arbitrary `obj` attribute carriers are unsupported payload values and must reach shared current payload validation.
- **On-demand context**: `src/parallax/domains/narrative_intel/ARCHITECTURE.md`, `src/parallax/domains/narrative_intel/repositories/narrative_repository.py`, `tests/unit/domains/narrative_intel/test_narrative_repository_sql_contract.py`, and shared current payload validation semantics.
- **Kill/defer criteria**: Stop if Narrative admissions intentionally support generic adapter objects, if psycopg `Jsonb` cannot be identified reliably, or if rejecting Jsonb-like values breaks a documented runtime payload source.
- **Eval/repair signal**: `getattr(value, "obj", value)` generic unwrapping, Jsonb-like test doubles passing as runtime payload truth, unsupported-value validation drift, and SDD generated index drift.
- **Implementation**: Replace generic `obj` attribute unwrapping with `isinstance(value, Jsonb)` before recursively unwrapping adapter payloads.
- **Verification**: `uv run pytest tests/unit/domains/narrative_intel/test_narrative_repository_sql_contract.py::test_admission_payload_hash_rejects_jsonb_like_legacy_adapter_values -q`
- **Review owner**: parent
- **Status**: [x]

### Task 167 — Macro daily brief hash uses shared current payload contract

- **File(s)**: `src/parallax/domains/macro_intel/repositories/macro_intel_repository.py`, `tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 166
- **Touch set**: `src/parallax/domains/macro_intel/repositories/macro_intel_repository.py`, `tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/domains/macro_intel/repositories/macro_intel_repository.py` for Macro daily brief current-row payload hash semantics and idempotent writes.
- **Failing test first**: `tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py::test_macro_daily_brief_payload_hash_rejects_legacy_payload_keys` — call `_macro_daily_brief_payload_hash()` with a non-string payload key and assert the shared current payload-key validation raises before the retired local normalizer can stringify compatibility-shaped daily brief payload keys.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Macro daily brief row hashing must use `stable_current_payload_hash()` from `src/parallax/platform/current_read_model_payload_hash.py`; the repository must not hash current `macro_daily_briefs` payloads through `postgres_safe_json()`, local key stringification, or generic `default=str` value conversion.
- **On-demand context**: `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `src/parallax/domains/macro_intel/repositories/macro_intel_repository.py`, `tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py`, and current read-model payload hash idempotency contracts.
- **Kill/defer criteria**: Stop if Macro daily briefs intentionally support non-string payload keys, if production daily brief payloads require compatibility key stringification at runtime, or if the shared hash helper cannot preserve unchanged hashes for compliant daily brief payloads.
- **Eval/repair signal**: `_macro_daily_brief_payload_hash()` using `postgres_safe_json()`, local key stringification, generic `default=str`, Macro daily brief idempotency drift, and SDD generated index drift.
- **Implementation**: Compute `macro_daily_briefs.payload_hash` with `stable_current_payload_hash()` while continuing to exclude `computed_at_ms` from the product payload hash.
- **Verification**: `uv run pytest tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py::test_macro_daily_brief_payload_hash_rejects_legacy_payload_keys -q`
- **Review owner**: parent
- **Status**: [x]

### Task 168 — Macro view snapshot hash uses shared current payload contract

- **File(s)**: `src/parallax/domains/macro_intel/repositories/macro_intel_repository.py`, `tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 167
- **Touch set**: `src/parallax/domains/macro_intel/repositories/macro_intel_repository.py`, `tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/domains/macro_intel/repositories/macro_intel_repository.py` for Macro view snapshot current-row payload hash semantics and idempotent writes.
- **Failing test first**: `tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py::test_macro_snapshot_payload_hash_rejects_legacy_feature_keys` — call `_macro_snapshot_payload_hash()` with `features_json` containing a non-string key and assert the shared current payload-key validation raises before the retired local normalizer can stringify compatibility-shaped snapshot payload keys.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Macro view snapshot row hashing must use `stable_current_payload_hash()` from `src/parallax/platform/current_read_model_payload_hash.py`; the repository must not hash current `macro_view_snapshots` payloads through `postgres_safe_json()`, local key stringification, or generic `default=str` value conversion.
- **On-demand context**: `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `src/parallax/domains/macro_intel/repositories/macro_intel_repository.py`, `tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py`, and current read-model payload hash idempotency contracts.
- **Kill/defer criteria**: Stop if Macro view snapshots intentionally support non-string snapshot JSON keys, if production snapshot payloads require compatibility key stringification at runtime, or if the shared hash helper cannot preserve unchanged hashes for compliant snapshot payloads.
- **Eval/repair signal**: `_macro_snapshot_payload_hash()` using `postgres_safe_json()`, local key stringification, generic `default=str`, Macro snapshot idempotency drift, and SDD generated index drift.
- **Implementation**: Compute `macro_view_snapshots.payload_hash` with `stable_current_payload_hash()` while preserving the existing explicit snapshot payload field list.
- **Verification**: `uv run pytest tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py::test_macro_snapshot_payload_hash_rejects_legacy_feature_keys -q`
- **Review owner**: parent
- **Status**: [x]

### Task 169 — Macro observation series row hash uses shared current payload contract

- **File(s)**: `src/parallax/domains/macro_intel/observation_identity.py`, `tests/unit/domains/macro_intel/test_macro_observation_identity.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 168
- **Touch set**: `src/parallax/domains/macro_intel/observation_identity.py`, `tests/unit/domains/macro_intel/test_macro_observation_identity.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/domains/macro_intel/observation_identity.py` for Macro observation series current-row payload hash semantics; coordinate with `src/parallax/domains/macro_intel/repositories/macro_intel_repository.py` for Macro observation series unchanged-write detection.
- **Failing test first**: `tests/unit/domains/macro_intel/test_macro_observation_identity.py::test_macro_series_current_row_payload_hash_rejects_legacy_raw_payload_keys` — call `macro_series_current_row_payload_hash()` with `raw_payload_json` containing a non-string key and assert the shared current payload-key validation raises before the retired local normalizer can stringify compatibility-shaped series-row payload keys.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Macro observation series row hashing must use `stable_current_payload_hash()` from `src/parallax/platform/current_read_model_payload_hash.py`; the current read model hash path must not use the local `_stable_payload_hash()` / `_json_ready()` compatibility normalizer that stringifies mapping keys, sorts unordered containers, or generically ISO-formats values.
- **On-demand context**: `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `src/parallax/domains/macro_intel/observation_identity.py`, `src/parallax/domains/macro_intel/repositories/macro_intel_repository.py`, `tests/unit/domains/macro_intel/test_macro_observation_identity.py`, and current read-model payload hash idempotency contracts.
- **Kill/defer criteria**: Stop if Macro observation series rows intentionally support non-string `raw_payload_json` keys, if production current rows require compatibility key stringification at runtime, or if the shared hash helper cannot preserve unchanged hashes for compliant series-row payloads.
- **Eval/repair signal**: `macro_series_current_row_payload_hash()` using local `_stable_payload_hash()`, local `_json_ready()` key stringification, unordered-container sorting, generic ISO formatting, Macro series row idempotency drift, and SDD generated index drift.
- **Implementation**: Compute `macro_observation_series_rows.payload_hash` with `stable_current_payload_hash()` while preserving the explicit current series row payload field list and leaving `macro_observation_fact_payload_hash()` for fact payload semantics.
- **Verification**: `uv run pytest tests/unit/domains/macro_intel/test_macro_observation_identity.py::test_macro_series_current_row_payload_hash_rejects_legacy_raw_payload_keys -q`
- **Review owner**: parent
- **Status**: [x]

### Task 170 — Token Radar stable hash uses shared current payload contract

- **File(s)**: `src/parallax/domains/token_intel/services/token_radar_payload_hash.py`, `tests/unit/test_token_radar_payload_hash.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 169
- **Touch set**: `src/parallax/domains/token_intel/services/token_radar_payload_hash.py`, `tests/unit/test_token_radar_payload_hash.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/domains/token_intel/services/token_radar_payload_hash.py` for Token Radar current payload hash canonicalization semantics; coordinate with `src/parallax/domains/token_intel/repositories/token_radar_repository.py` for current row payload hash and stable generation semantics; coordinate with `src/parallax/domains/token_intel/services/token_radar_projection.py` for downstream dirty-target payload hash semantics.
- **Failing test first**: `tests/unit/test_token_radar_payload_hash.py::test_hash_rejects_legacy_non_string_payload_keys` and `tests/unit/test_token_radar_payload_hash.py::test_hash_rejects_unordered_payload_containers` — call `stable_token_radar_payload_hash()` with compatibility-shaped non-string mapping keys and unordered containers and assert shared current payload validation raises before Token Radar canonicalization can stringify or sort them into serving hashes.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Token Radar current payload hashing must use `stable_current_payload_hash()` from `src/parallax/platform/current_read_model_payload_hash.py` after product-specific canonical removal of `factor_snapshot_json.provenance.computed_at_ms`; the helper must not keep local final hash generation, mapping-key stringification, unordered-container sorting, or generic adapter-object unwrapping before current row, stable generation, Pulse trigger, Narrative admission, token profile current, or capture-tier dirty-target hashes are generated.
- **On-demand context**: `src/parallax/domains/token_intel/ARCHITECTURE.md`, `src/parallax/domains/token_intel/services/token_radar_payload_hash.py`, `src/parallax/domains/token_intel/repositories/token_radar_repository.py`, `src/parallax/domains/token_intel/services/token_radar_projection.py`, `tests/unit/test_token_radar_payload_hash.py`, and current read-model payload hash idempotency contracts.
- **Kill/defer criteria**: Stop if Token Radar payload hashes intentionally support non-string JSON keys or unordered containers, if production current rows require compatibility key stringification at runtime, or if the shared hash helper cannot preserve the product-required factor snapshot computed timestamp exclusion for compliant payloads.
- **Eval/repair signal**: local Token Radar sha256 JSON dump, local canonical key stringification, unordered-container sorting, generic `.obj` unwrapping, token_radar_current_rows idempotency drift, downstream dirty-target hash drift, stable generation id drift, and SDD generated index drift.
- **Implementation**: Delegate `stable_token_radar_payload_hash()` final hash generation to `stable_current_payload_hash()`, reject non-string keys and unordered containers before canonicalization, unwrap only real `Jsonb` adapters, and keep the existing factor snapshot computed timestamp exclusion.
- **Verification**: `uv run pytest tests/unit/test_token_radar_payload_hash.py::test_hash_rejects_legacy_non_string_payload_keys tests/unit/test_token_radar_payload_hash.py::test_hash_rejects_unordered_payload_containers -q`
- **Review owner**: parent
- **Status**: [x]

### Task 171 — Shared current hash exits runtime import boundary

- **File(s)**: `src/parallax/platform/current_read_model_payload_hash.py`, `src/parallax/app/runtime/current_read_model_publisher.py`, `src/parallax/domains/news_intel/repositories/news_repository.py`, `src/parallax/domains/macro_intel/repositories/macro_intel_repository.py`, `src/parallax/domains/asset_market/repositories/token_profile_current_repository.py`, `src/parallax/domains/cex_market_intel/repositories/cex_detail_snapshot_repository.py`, `src/parallax/domains/cex_market_intel/repositories/cex_oi_radar_repository.py`, `src/parallax/domains/narrative_intel/repositories/narrative_repository.py`, `src/parallax/domains/macro_intel/observation_identity.py`, `src/parallax/domains/token_intel/services/token_radar_payload_hash.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 170
- **Touch set**: `src/parallax/platform/current_read_model_payload_hash.py`, `src/parallax/app/runtime/current_read_model_publisher.py`, `src/parallax/domains/news_intel/repositories/news_repository.py`, `src/parallax/domains/macro_intel/repositories/macro_intel_repository.py`, `src/parallax/domains/asset_market/repositories/token_profile_current_repository.py`, `src/parallax/domains/cex_market_intel/repositories/cex_detail_snapshot_repository.py`, `src/parallax/domains/cex_market_intel/repositories/cex_oi_radar_repository.py`, `src/parallax/domains/narrative_intel/repositories/narrative_repository.py`, `src/parallax/domains/macro_intel/observation_identity.py`, `src/parallax/domains/token_intel/services/token_radar_payload_hash.py`, `tests/architecture/test_worker_manifest_static_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/app/runtime/current_read_model_publisher.py` for current read-model publisher row hashing semantics; coordinate with `src/parallax/platform/current_read_model_payload_hash.py` for shared current payload hash contract ownership; coordinate with `tests/architecture/test_src_domain_architecture.py` for repository upward-import boundary semantics.
- **Failing test first**: `tests/architecture/test_src_domain_architecture.py::test_repositories_and_queries_do_not_import_services_or_runtime` — run the repository/query upward-import architecture gate and assert domain repositories no longer import the shared current payload hash helper from `parallax.app.runtime.current_read_model_publisher`.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: The pure current payload hash contract must live below app/runtime in `src/parallax/platform/current_read_model_payload_hash.py`; domain repositories and services may import that platform helper, while `CurrentReadModelPublisher` remains in `src/parallax/app/runtime/current_read_model_publisher.py` and delegates row payload hashing to the platform helper. No domain repository or query may import `parallax.app.runtime.current_read_model_publisher` for shared payload hash behavior.
- **On-demand context**: `tests/architecture/test_src_domain_architecture.py`, `src/parallax/platform/current_read_model_payload_hash.py`, `src/parallax/app/runtime/current_read_model_publisher.py`, current hash-consuming repositories, and shared payload hash SDD tasks.
- **Kill/defer criteria**: Stop if platform helpers are forbidden in domain repositories, if `CurrentReadModelPublisher` cannot delegate without duplicating hash logic, or if moving the pure hash contract changes validation errors or current payload hash shape for compliant payloads.
- **Eval/repair signal**: repository upward-import architecture failures, domain imports of `parallax.app.runtime.current_read_model_publisher`, duplicated stable payload hash logic, publisher row payload hash drift, and SDD generated index drift.
- **Implementation**: Move `stable_current_payload_hash()`, payload-hash constants, recursive payload validation, and JSON canonicalization into `src/parallax/platform/current_read_model_payload_hash.py`; update runtime publisher, domain repositories/services, and tests to import the platform helper while preserving `CurrentReadModelPublisher` behavior.
- **Verification**: `uv run pytest tests/architecture/test_src_domain_architecture.py::test_repositories_and_queries_do_not_import_services_or_runtime -q`
- **Review owner**: parent
- **Status**: [x]

### Task 172 — Token Radar dirty queues use shared strict payload hash

- **File(s)**: `src/parallax/domains/token_intel/repositories/token_radar_dirty_target_repository.py`, `src/parallax/domains/token_intel/repositories/token_radar_source_dirty_event_repository.py`, `tests/unit/test_token_radar_dirty_target_repository.py`, `tests/unit/domains/token_intel/test_token_radar_source_dirty_events.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 171
- **Touch set**: `src/parallax/domains/token_intel/repositories/token_radar_dirty_target_repository.py`, `src/parallax/domains/token_intel/repositories/token_radar_source_dirty_event_repository.py`, `tests/unit/test_token_radar_dirty_target_repository.py`, `tests/unit/domains/token_intel/test_token_radar_source_dirty_events.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/domains/token_intel/runtime/token_radar_projection_worker.py` for dirty-target claim/done semantics; coordinate with `src/parallax/domains/token_intel/services/token_radar_projection.py` for downstream dirty-target payload hash semantics; coordinate with `src/parallax/platform/current_read_model_payload_hash.py` for shared current payload hash validation shape.
- **Failing test first**: `tests/unit/test_token_radar_dirty_target_repository.py::test_dirty_payload_hash_rejects_legacy_non_string_payload_keys` and `tests/unit/domains/token_intel/test_token_radar_source_dirty_events.py::test_source_dirty_event_payload_hash_rejects_legacy_non_string_payload_keys` — call dirty queue payload hash helpers with compatibility-shaped non-string mapping keys and assert shared current payload validation raises before local key stringification or JSON sanitation.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Domain implementation
- **Deterministic constraints**: Token Radar dirty target and source dirty event queue hashes must keep lifecycle fields out of the stable payload, but lifecycle filtering must require string keys first and final hash generation must use `stable_dirty_target_payload_hash()` from `src/parallax/platform/current_read_model_payload_hash.py`. The helpers must not call `postgres_safe_json()`, stringify mapping keys, or preserve local `hashlib`/`json.dumps` canonicalization as a compatibility path.
- **On-demand context**: `src/parallax/domains/token_intel/ARCHITECTURE.md`, `docs/agent-playbook/read-model-change-checklist.md`, `src/parallax/domains/token_intel/repositories/token_radar_dirty_target_repository.py`, `src/parallax/domains/token_intel/repositories/token_radar_source_dirty_event_repository.py`, `tests/unit/test_token_radar_dirty_target_repository.py`, `tests/unit/domains/token_intel/test_token_radar_source_dirty_events.py`, and current read-model payload hash idempotency contracts.
- **Kill/defer criteria**: Stop if dirty queue hash payloads intentionally accept non-string keys for a live producer, if lifecycle fields need to remain in queue no-op hashes, or if the shared strict hash changes claim/done matching for compliant dirty queue rows.
- **Eval/repair signal**: dirty queue local sha256 JSON dump, `str(key)` filtering, `postgres_safe_json()` sanitation before hash, queue payload hash drift, claim/done mismatch, source dirty event coalescing drift, and SDD generated index drift.
- **Implementation**: Compute Token Radar dirty target and source dirty event queue `payload_hash` values with `stable_dirty_target_payload_hash()` after strict lifecycle-field filtering, and add RED tests proving legacy non-string key payloads are rejected before compatibility normalization.
- **Verification**: `uv run pytest tests/unit/test_token_radar_dirty_target_repository.py::test_dirty_payload_hash_rejects_legacy_non_string_payload_keys tests/unit/domains/token_intel/test_token_radar_source_dirty_events.py::test_source_dirty_event_payload_hash_rejects_legacy_non_string_payload_keys -q`
- **Review owner**: parent
- **Status**: [x]

### Task 173 — Pulse trigger dirty queue hash excludes lifecycle state

- **File(s)**: `src/parallax/domains/pulse_lab/repositories/pulse_trigger_dirty_target_repository.py`, `tests/unit/domains/pulse_lab/test_pulse_trigger_dirty_target_repository.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 172
- **Touch set**: `src/parallax/domains/pulse_lab/repositories/pulse_trigger_dirty_target_repository.py`, `tests/unit/domains/pulse_lab/test_pulse_trigger_dirty_target_repository.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py` for dirty-trigger claim/done semantics; coordinate with `src/parallax/domains/token_intel/services/token_radar_projection.py` for Pulse trigger enqueue payload semantics; coordinate with `src/parallax/platform/current_read_model_payload_hash.py` for shared current payload hash validation shape.
- **Failing test first**: `tests/unit/domains/pulse_lab/test_pulse_trigger_dirty_target_repository.py::test_payload_hash_rejects_legacy_non_string_payload_keys` and `tests/unit/domains/pulse_lab/test_pulse_trigger_dirty_target_repository.py::test_payload_hash_ignores_queue_lifecycle_fields` — call the Pulse trigger dirty payload hash helper with compatibility-shaped non-string mapping keys and queue lifecycle drift and assert shared current payload validation plus lifecycle exclusion.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Domain implementation
- **Deterministic constraints**: Pulse trigger dirty target queue hashes must keep business trigger fields (`target_type`, `target_id`, `window`, `scope`, `source_watermark_ms`, `dirty_reason`) in the stable payload while excluding queue lifecycle/scheduling state (`priority`, `due_at_ms`, `leased_until_ms`, `lease_owner`, `attempt_count`, `last_error`, `first_dirty_at_ms`, `updated_at_ms`). Final hash generation must use `stable_dirty_target_payload_hash()` from `src/parallax/platform/current_read_model_payload_hash.py` and must not preserve `postgres_safe_json()`, local key stringification, or repository-local sha256 JSON canonicalization as a compatibility path.
- **On-demand context**: `src/parallax/domains/pulse_lab/ARCHITECTURE.md`, `docs/WORKER_FLOW.md`, `docs/WORKERS.md`, `docs/agent-playbook/read-model-change-checklist.md`, `src/parallax/domains/pulse_lab/repositories/pulse_trigger_dirty_target_repository.py`, `src/parallax/domains/pulse_lab/runtime/pulse_candidate_worker.py`, and Pulse trigger dirty-target tests.
- **Kill/defer criteria**: Stop if Pulse trigger hashes intentionally include scheduling lifecycle state for stale-completion protection, if runtime producers require non-string payload keys, or if shared hash prefix changes break claim/done matching for compliant queue rows.
- **Eval/repair signal**: Pulse trigger local sha256 JSON dump, `postgres_safe_json()` sanitation before hash, non-string key acceptance, lifecycle fields in queue payload hash, stale completion drift, dirty trigger lease reset drift, and SDD generated index drift.
- **Implementation**: Compute Pulse trigger dirty target `payload_hash` values with `stable_dirty_target_payload_hash()` after strict lifecycle-field filtering, and add RED tests proving legacy non-string key payloads are rejected and scheduling lifecycle changes do not alter the stable dirty payload hash.
- **Verification**: `uv run pytest tests/unit/domains/pulse_lab/test_pulse_trigger_dirty_target_repository.py::test_payload_hash_rejects_legacy_non_string_payload_keys tests/unit/domains/pulse_lab/test_pulse_trigger_dirty_target_repository.py::test_payload_hash_ignores_queue_lifecycle_fields -q`
- **Review owner**: parent
- **Status**: [x]

### Task 174 — Narrative admission dirty queue hash excludes lifecycle state

- **File(s)**: `src/parallax/domains/narrative_intel/repositories/narrative_admission_dirty_target_repository.py`, `tests/unit/domains/narrative_intel/test_narrative_dirty_target_repositories.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 173
- **Touch set**: `src/parallax/domains/narrative_intel/repositories/narrative_admission_dirty_target_repository.py`, `tests/unit/domains/narrative_intel/test_narrative_dirty_target_repositories.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `src/parallax/domains/narrative_intel/runtime/narrative_admission_worker.py` for dirty-target claim/done semantics; coordinate with `src/parallax/domains/token_intel/services/token_radar_projection.py` for Narrative admission enqueue payload semantics; coordinate with `src/parallax/platform/current_read_model_payload_hash.py` for shared current payload hash validation shape.
- **Failing test first**: `tests/unit/domains/narrative_intel/test_narrative_dirty_target_repositories.py::test_payload_hash_rejects_legacy_non_string_payload_keys` and `tests/unit/domains/narrative_intel/test_narrative_dirty_target_repositories.py::test_payload_hash_ignores_queue_lifecycle_fields` — call the Narrative admission dirty payload hash helper with compatibility-shaped non-string mapping keys and queue lifecycle drift and assert shared current payload validation plus lifecycle exclusion.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Domain implementation
- **Deterministic constraints**: Narrative admission dirty target queue hashes must keep business trigger fields (`target_type`, `target_id`, `window`, `scope`, `projection_version`, `schema_version`, `source_watermark_ms`, `dirty_reason`) in the stable payload while excluding queue lifecycle/scheduling state (`priority`, `due_at_ms`, `leased_until_ms`, `lease_owner`, `attempt_count`, `last_error`, `first_dirty_at_ms`, `updated_at_ms`). Final hash generation must use `stable_dirty_target_payload_hash()` from `src/parallax/platform/current_read_model_payload_hash.py` and must not preserve `postgres_safe_json()`, local key stringification, or repository-local sha256 JSON canonicalization as a compatibility path.
- **On-demand context**: `src/parallax/domains/narrative_intel/ARCHITECTURE.md`, `docs/WORKER_FLOW.md`, `docs/WORKERS.md`, `docs/agent-playbook/read-model-change-checklist.md`, `src/parallax/domains/narrative_intel/repositories/narrative_admission_dirty_target_repository.py`, `src/parallax/domains/narrative_intel/runtime/narrative_admission_worker.py`, and Narrative dirty-target tests.
- **Kill/defer criteria**: Stop if Narrative dirty hashes intentionally include scheduling lifecycle state for stale-completion protection, if runtime producers require non-string payload keys, or if shared hash prefix changes break claim/done matching for compliant queue rows.
- **Eval/repair signal**: Narrative dirty local sha256 JSON dump, `postgres_safe_json()` sanitation before hash, non-string key acceptance, lifecycle fields in queue payload hash, stale completion drift, dirty-target lease reset drift, and SDD generated index drift.
- **Implementation**: Compute Narrative admission dirty target `payload_hash` values with `stable_dirty_target_payload_hash()` after strict lifecycle-field filtering, and add RED tests proving legacy non-string key payloads are rejected and scheduling lifecycle changes do not alter the stable dirty payload hash.
- **Verification**: `uv run pytest tests/unit/domains/narrative_intel/test_narrative_dirty_target_repositories.py::test_payload_hash_rejects_legacy_non_string_payload_keys tests/unit/domains/narrative_intel/test_narrative_dirty_target_repositories.py::test_payload_hash_ignores_queue_lifecycle_fields -q`
- **Review owner**: parent
- **Status**: [x]

### Task 175 — Asset Market dirty-control-plane hashes use shared strict payload hash

- **File(s)**: `src/parallax/platform/current_read_model_payload_hash.py`, `src/parallax/domains/asset_market/repositories/market_tick_current_dirty_target_repository.py`, `src/parallax/domains/asset_market/repositories/token_profile_current_dirty_target_repository.py`, `src/parallax/domains/asset_market/repositories/token_image_source_dirty_target_repository.py`, `src/parallax/domains/asset_market/repositories/asset_profile_refresh_target_repository.py`, `src/parallax/domains/token_intel/repositories/token_radar_dirty_target_repository.py`, `src/parallax/domains/token_intel/repositories/token_radar_source_dirty_event_repository.py`, `src/parallax/domains/pulse_lab/repositories/pulse_trigger_dirty_target_repository.py`, `src/parallax/domains/narrative_intel/repositories/narrative_admission_dirty_target_repository.py`, `tests/unit/domains/asset_market/test_asset_market_dirty_target_payload_hashes.py`, `tests/unit/domains/token_intel/test_token_radar_dirty_target_kinds.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 174
- **Touch set**: `src/parallax/platform/current_read_model_payload_hash.py`, `src/parallax/domains/asset_market/repositories/market_tick_current_dirty_target_repository.py`, `src/parallax/domains/asset_market/repositories/token_profile_current_dirty_target_repository.py`, `src/parallax/domains/asset_market/repositories/token_image_source_dirty_target_repository.py`, `src/parallax/domains/asset_market/repositories/asset_profile_refresh_target_repository.py`, `src/parallax/domains/token_intel/repositories/token_radar_dirty_target_repository.py`, `src/parallax/domains/token_intel/repositories/token_radar_source_dirty_event_repository.py`, `src/parallax/domains/pulse_lab/repositories/pulse_trigger_dirty_target_repository.py`, `src/parallax/domains/narrative_intel/repositories/narrative_admission_dirty_target_repository.py`, `tests/unit/domains/asset_market/test_asset_market_dirty_target_payload_hashes.py`, `tests/unit/domains/token_intel/test_token_radar_dirty_target_kinds.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: `src/parallax/domains/asset_market/runtime/market_tick_current_projection_worker.py`, `src/parallax/domains/asset_market/runtime/token_profile_current_worker.py`, `src/parallax/domains/asset_market/runtime/token_image_mirror_worker.py`, `src/parallax/domains/asset_market/runtime/asset_profile_refresh_worker.py`, `src/parallax/platform/current_read_model_payload_hash.py`
- **Failing test first**: `tests/unit/domains/asset_market/test_asset_market_dirty_target_payload_hashes.py::test_asset_market_dirty_payload_hashes_reject_legacy_non_string_keys`, `tests/unit/domains/asset_market/test_asset_market_dirty_target_payload_hashes.py::test_asset_market_dirty_payload_hashes_ignore_queue_lifecycle_fields`, and `tests/unit/domains/asset_market/test_asset_market_dirty_target_payload_hashes.py::test_token_image_source_dirty_target_rejects_legacy_raw_ref_keys_before_json_safety` — parameterize Asset Market dirty queue hash helpers with non-string payload keys, queue lifecycle drift, and token-image `raw_ref_json` compatibility keys and assert shared current payload validation plus lifecycle exclusion before JSON safety.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Domain implementation
- **Deterministic constraints**: Asset Market dirty queue hashes must keep business trigger fields (`target_type`, `target_id`, source/provider identity, source watermark, and dirty reason) in the stable payload while excluding queue lifecycle/scheduling state (`priority`, `due_at_ms`, `leased_until_ms`, `lease_owner`, `attempt_count`, `last_error`, `first_dirty_at_ms`, `updated_at_ms`, and `dirty_at_ms`). Final hash generation must use the platform `stable_dirty_target_payload_hash()` helper and must not preserve `postgres_safe_json()`, `default=str`, local key stringification, or repository-local sha256 JSON canonicalization as a compatibility path. Token image source rows must validate raw `raw_ref_json` keys before DB JSON sanitation.
- **On-demand context**: `src/parallax/domains/asset_market/ARCHITECTURE.md`, `docs/WORKER_FLOW.md`, `docs/WORKERS.md`, `docs/agent-playbook/read-model-change-checklist.md`, Asset Market dirty-target repositories, and current read-model payload hash idempotency contracts.
- **Kill/defer criteria**: Stop if an Asset Market dirty queue intentionally requires scheduling lifecycle state in the stale-completion hash, if a runtime producer still emits non-string payload keys, or if changing to the shared `sha256:` contract breaks compliant claim/done matching.
- **Eval/repair signal**: Asset Market dirty queue local sha256 JSON dumps, `postgres_safe_json()` sanitation before hash, `default=str` hash normalization, stale tests expecting bare 64-character hashes, dirty queue lifecycle fields changing payload hashes, token-image raw-ref key sanitation before validation, and SDD generated index drift.
- **Implementation**: Add `stable_dirty_target_payload_hash()` beside the shared current payload hash helper, switch Asset Market dirty queue hash helpers to it, validate token-image raw refs before JSON safety, and collapse Token Radar/Pulse/Narrative dirty queues onto the shared helper to avoid duplicate lifecycle filters.
- **Verification**: `uv run pytest tests/unit/domains/asset_market/test_asset_market_dirty_target_payload_hashes.py tests/unit/domains/token_intel/test_token_radar_dirty_target_kinds.py::test_dirty_payload_hash_excludes_queue_lifecycle_fields -q`
- **Review owner**: parent
- **Status**: [x]

### Task 176 — Token Capture Tier dirty rank-set fingerprint uses shared strict payload hash

- **File(s)**: `src/parallax/domains/asset_market/repositories/token_capture_tier_dirty_target_repository.py`, `tests/unit/test_token_radar_projection.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 175
- **Touch set**: `src/parallax/domains/asset_market/repositories/token_capture_tier_dirty_target_repository.py`, `tests/unit/test_token_radar_projection.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: `src/parallax/domains/asset_market/runtime/token_capture_tier_worker.py`, `src/parallax/domains/token_intel/services/token_radar_projection.py`, `src/parallax/platform/current_read_model_payload_hash.py`
- **Failing test first**: `tests/unit/test_token_radar_projection.py::test_capture_tier_rank_set_fingerprint_uses_shared_payload_hash_contract`, `tests/unit/test_token_radar_projection.py::test_capture_tier_rank_set_fingerprint_rejects_legacy_factor_snapshot_keys`, and `tests/unit/test_token_radar_projection.py::test_capture_tier_rank_set_fingerprint_rejects_unordered_payload_containers` — call the rank-set dirty fingerprint with compliant rows, compatibility-shaped nested keys, and unordered containers and assert the shared `sha256:` contract plus strict payload validation.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Domain implementation
- **Deterministic constraints**: Token Capture Tier dirty rank-set fingerprints must keep stable business rank fields and live-market keys, continue to ignore `factor_snapshot_json.provenance.computed_at_ms`, continue to normalize numeric rank scores through `_rank_score_payload()`, and use `stable_current_payload_hash()` for final fingerprint generation. The implementation must not preserve `_json_ready()` key stringification, set-to-list conversion, generic adapter unwrapping, or repository-local `json.dumps()`/`hashlib.sha256()` canonicalization as a compatibility path.
- **On-demand context**: `src/parallax/domains/asset_market/ARCHITECTURE.md`, `docs/WORKER_FLOW.md`, `docs/WORKERS.md`, `docs/agent-playbook/read-model-change-checklist.md`, `src/parallax/domains/asset_market/repositories/token_capture_tier_dirty_target_repository.py`, `src/parallax/domains/asset_market/runtime/token_capture_tier_worker.py`, and rank-set fingerprint tests in `tests/unit/test_token_radar_projection.py`.
- **Kill/defer criteria**: Stop if rank-set fingerprints intentionally accept non-string factor-snapshot keys from a live producer, if unordered containers are required for compliant rank input rows, or if switching to the shared `sha256:` contract breaks compliant dirty claim/done matching.
- **Eval/repair signal**: local `_json_ready()` compatibility normalizer, bare 64-character dirty fingerprints, non-string key acceptance, unordered container acceptance, computed-at drift in factor snapshots, rank-set dirty queue claim/done mismatch, and SDD generated index drift.
- **Implementation**: Replace Token Capture Tier rank-set and row-product local JSON/sha256 fingerprinting with `stable_current_payload_hash()`, delete `_json_ready()`, preserve product-specific stable fields, and add RED tests for shared hash shape plus compatibility payload rejection.
- **Verification**: `uv run pytest tests/unit/test_token_radar_projection.py::test_capture_tier_rank_set_fingerprint_uses_shared_payload_hash_contract tests/unit/test_token_radar_projection.py::test_capture_tier_rank_set_fingerprint_rejects_legacy_factor_snapshot_keys tests/unit/test_token_radar_projection.py::test_capture_tier_rank_set_fingerprint_rejects_unordered_payload_containers -q`
- **Review owner**: parent
- **Status**: [x]

### Task 177 — Macro projection dirty targets use shared strict dirty payload hash

- **File(s)**: `src/parallax/domains/macro_intel/repositories/macro_intel_repository.py`, `tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 176
- **Touch set**: `src/parallax/domains/macro_intel/repositories/macro_intel_repository.py`, `tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: `src/parallax/domains/macro_intel/runtime/macro_view_projection_worker.py`, `src/parallax/platform/current_read_model_payload_hash.py`, `src/parallax/domains/macro_intel/observation_identity.py`
- **Failing test first**: `tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py::test_enqueue_macro_projection_dirty_target_coalesces_current_target`, `tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py::test_macro_projection_dirty_payload_hash_rejects_legacy_payload_shapes`, `tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py::test_enqueue_macro_projection_dirty_targets_for_changes_groups_by_concept_watermark`, and `tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py::test_macro_projection_dirty_change_payload_hash_rejects_legacy_payload_shapes` — enqueue current and concept dirty targets and call the dirty hash helpers with compatibility-shaped values, asserting the shared `sha256:` dirty payload contract and strict nested-key validation.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Domain implementation
- **Deterministic constraints**: Macro projection dirty target hashes must keep stable business control-plane fields (`projection_name`, `projection_version`, `target_kind`, `target_id`, concept/date watermarks, dirty reason, and source watermark) while using `stable_dirty_target_payload_hash()` for final hash generation. The implementation must not preserve `postgres_safe_json()`, `default=str`, local key stringification, or repository-local `json.dumps()`/`hashlib.sha256()` canonicalization as a dirty-target compatibility path.
- **On-demand context**: `src/parallax/domains/macro_intel/ARCHITECTURE.md`, `docs/WORKER_FLOW.md`, `docs/WORKERS.md`, `docs/agent-playbook/read-model-change-checklist.md`, `src/parallax/domains/macro_intel/repositories/macro_intel_repository.py`, and macro dirty queue tests in `tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py`.
- **Kill/defer criteria**: Stop if Macro producers intentionally require non-string nested dirty-reason payload keys, if compliant dirty claim/done matching cannot accept the shared `sha256:` hash contract, or if current and concept dirty targets need different platform hash semantics.
- **Eval/repair signal**: bare 64-character Macro dirty target hashes, `_macro_projection_dirty_*_payload_hash()` using `postgres_safe_json()` or `default=str`, compatibility-shaped nested keys being accepted, claim/done payload-hash mismatch, and SDD generated index drift.
- **Implementation**: Import `stable_dirty_target_payload_hash()` from the platform hash contract, switch current and concept Macro projection dirty hash helpers to it, and add RED tests for shared hash shape plus compatibility payload rejection.
- **Verification**: `uv run pytest tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py::test_enqueue_macro_projection_dirty_target_coalesces_current_target tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py::test_macro_projection_dirty_payload_hash_rejects_legacy_payload_shapes tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py::test_enqueue_macro_projection_dirty_targets_for_changes_groups_by_concept_watermark tests/unit/domains/macro_intel/test_macro_sync_repository_sql.py::test_macro_projection_dirty_change_payload_hash_rejects_legacy_payload_shapes -q`
- **Review owner**: parent
- **Status**: [x]

### Task 178 — Agent execution docs name the live read-only tool contract

- **File(s)**: `docs/AGENT_EXECUTION.md`, `tests/architecture/test_agent_execution_plane_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 177
- **Touch set**: `docs/AGENT_EXECUTION.md`, `tests/architecture/test_agent_execution_plane_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: `src/parallax/platform/agent_read_tools.py`, `docs/agent-playbook/task-reading-matrix.md`
- **Failing test first**: `tests/architecture/test_agent_execution_plane_contracts.py::test_agent_execution_doc_names_current_read_tool_contract` — parse `src/parallax/platform/agent_read_tools.py`, require `docs/AGENT_EXECUTION.md` to mention the live `ReadOnlySqlAgentTool` class, and reject the stale `AgentReadTool` class name.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Docs/contracts
- **Deterministic constraints**: Product-agent execution docs must name live source symbols for the read-only context registry and must not advertise stale class names that are no longer exported by `agent_read_tools.py`. This is a docs/source alignment gate, not a runtime product-agent tool-loop expansion.
- **On-demand context**: `docs/AGENT_EXECUTION.md`, `src/parallax/platform/agent_read_tools.py`, `tests/architecture/test_agent_execution_plane_contracts.py`, and `docs/agent-playbook/task-reading-matrix.md`.
- **Kill/defer criteria**: Stop if the source intentionally reintroduces an `AgentReadTool` compatibility alias, if product agents start receiving callable model tools, or if the read-only registry moves to a different owning module.
- **Eval/repair signal**: stale `AgentReadTool` references, missing `ReadOnlySqlAgentTool` documentation, read-only registry docs drifting from exported source symbols, and SDD generated index drift.
- **Implementation**: Add an architecture doc/source alignment test and update `docs/AGENT_EXECUTION.md` to name `ReadOnlySqlAgentTool`.
- **Verification**: `uv run pytest tests/architecture/test_agent_execution_plane_contracts.py::test_agent_execution_doc_names_current_read_tool_contract -q`
- **Review owner**: parent
- **Status**: [x]

### Task 179 — Active SDD current paths exclude removed files

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/_templates/tasks-template.md`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 178
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/_templates/tasks-template.md`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: `scripts/regen_sdd_work_index.py`; `docs/sdd/_templates/README.md`
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_tasks_reject_missing_current_file_and_touch_paths`, `tests/architecture/test_sdd_artifact_validator.py::test_tasks_allow_removed_file_records_outside_current_touch_surface`, and `tests/architecture/test_sdd_artifact_validator.py::test_tasks_allow_current_glob_touch_paths_when_they_match` — build active SDD fixtures with stale paths, removed-file records, and matching glob touch paths to prove current coordination surfaces cannot advertise deleted files.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Active task `File(s)` and `Touch set` entries must resolve to current repository paths or matching glob patterns; deleted artifacts belong in optional `Removed file(s)` and must not remain in generated coordination touch surfaces. The generated work index must continue to render only active touch sets.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `docs/sdd/_templates/tasks-template.md`, and active SDD task records for deleted-file tasks.
- **Kill/defer criteria**: Stop if historical completed records need to advertise deleted files, if a current touch glob intentionally matches nothing, or if the generated index starts rendering removed-file evidence as editable coordination scope.
- **Eval/repair signal**: missing current path issue, stale root visual artifacts in generated index, deleted runtime shim in active touch set, glob false negative, and SDD generated index drift.
- **Implementation**: Add active path existence/glob validation, add optional `Removed file(s)` validation, update the tasks template, move deleted Task61/Task115 paths into `Removed file(s)`, and regenerate the SDD work index.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_tasks_reject_missing_current_file_and_touch_paths tests/architecture/test_sdd_artifact_validator.py::test_tasks_allow_removed_file_records_outside_current_touch_surface tests/architecture/test_sdd_artifact_validator.py::test_tasks_allow_current_glob_touch_paths_when_they_match -q`
- **Review owner**: parent
- **Status**: [x]

### Task 180 — SDD lifecycle gates have first-class CLI checks

- **File(s)**: `scripts/check_sdd_gate.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/WORKFLOW.md`, `docs/sdd/README.md`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 179
- **Touch set**: `scripts/check_sdd_gate.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/WORKFLOW.md`, `docs/sdd/README.md`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: `scripts/validate_sdd_artifacts.py`; `scripts/dispatch_sdd_task.py`; `scripts/build_agent_context_packet.py`
- **Failing test first**: `tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_accepts_individual_gates` and `tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_failed_analyze_gate` — run a production-style active SDD fixture through `clarify`, `checklist`, `analyze`, and `implement` gate checks and prove a failed Analyze Gate exits non-zero.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `clarify`, `checklist`, `analyze`, and `implement` must be checkable through a non-mutating CLI for one feature without requiring the final verification lane. Analyze failure detection must bind to gate result cells, not historical RED/GREEN evidence text.
- **On-demand context**: `docs/WORKFLOW.md`, `docs/sdd/README.md`, `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_agent_playbook_contracts.py`, and Spec Kit-style gate sequence references in the active spec background.
- **Kill/defer criteria**: Stop if the CLI mutates artifacts, if it duplicates final `make check-all` verification semantics, if it accepts failed Analyze rows, or if it replaces the full SDD validator rather than narrowing gate feedback.
- **Eval/repair signal**: missing gate CLI, Analyze Gate false positive/negative, context fixture path-currentness failure, SDD docs missing command surface, and generated index drift.
- **Implementation**: Add `scripts/check_sdd_gate.py`, add subprocess architecture tests for pass/fail gate behavior, document the gate commands in `docs/WORKFLOW.md` and `docs/sdd/README.md`, and keep `validate_sdd_artifacts.py` as the full-record validator.
- **Verification**: `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_accepts_individual_gates tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_failed_analyze_gate -q`
- **Review owner**: parent
- **Status**: [x]

### Task 181 — Tasks stop duplicating final verification evidence

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/_templates/tasks-template.md`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`
- **Owner**: parent
- **Depends on**: Task 180
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/_templates/tasks-template.md`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: `docs/sdd/_templates/verification-template.md`; `scripts/check_sdd_gate.py`; `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut/verification.md`
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_tasks_reject_final_verification_checklist_duplication` and `tests/architecture/test_agent_playbook_contracts.py::test_tasks_template_does_not_duplicate_final_verification_surface` — prove active task artifacts and the tasks template cannot maintain a duplicate final verification checklist outside `verification.md`.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `tasks.md` may describe task-level verification commands, but final completion evidence must live only in `verification.md`; the validator must reject `## Final verification` in task artifacts and the template must not teach future copies to recreate it.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, `docs/sdd/_templates/tasks-template.md`, `docs/sdd/_templates/verification-template.md`, and the active feature `verification.md`.
- **Kill/defer criteria**: Stop if the rule blocks task-level `Verification` fields, if it weakens `verification.md` completion gates, or if it treats historical RED/GREEN evidence as final `make check-all` evidence.
- **Eval/repair signal**: duplicated final verification checklist, stale template guidance, generated index issue-code drift, and false-green completion evidence split between tasks and verification artifacts.
- **Implementation**: Add the `tasks-final-verification-duplicated` validator issue, document its generated-index meaning, remove the duplicate `## Final verification` section from the tasks template and active task record, and keep final command evidence anchored in `verification.md`.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_tasks_reject_final_verification_checklist_duplication tests/architecture/test_agent_playbook_contracts.py::test_tasks_template_does_not_duplicate_final_verification_surface -q`
- **Review owner**: parent
- **Status**: [x]

### Task 182 — All active SDD gates run in check-all

- **File(s)**: `Makefile`, `scripts/check_sdd_gate.py`, `tests/architecture/test_harness_structure.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/WORKFLOW.md`, `docs/sdd/README.md`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`
- **Owner**: parent
- **Depends on**: Task 181
- **Touch set**: `Makefile`, `scripts/check_sdd_gate.py`, `tests/architecture/test_harness_structure.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/WORKFLOW.md`, `docs/sdd/README.md`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: `scripts/validate_sdd_artifacts.py`; `scripts/regen_sdd_work_index.py`; `docs/sdd/features/active/2026-06-09-agent-playbook-skill-hard-cut/tasks.md`
- **Failing test first**: `tests/architecture/test_harness_structure.py::test_make_check_all_runs_executable_sdd_harness`, `tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_accepts_all_active_features`, and `tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_any_failed_active_feature` — prove `check-all` invokes the all-active gate sweep and the CLI checks every active feature rather than only one happy path.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `check-all` must run `scripts/check_sdd_gate.py --all-active --check` before generated index freshness; the all-active CLI must run `clarify`, `checklist`, `analyze`, and `implement` for every active feature and return non-zero if any one feature fails.
- **On-demand context**: `Makefile`, `scripts/check_sdd_gate.py`, `docs/WORKFLOW.md`, `docs/sdd/README.md`, and active SDD feature records.
- **Kill/defer criteria**: Stop if all-active gate checking mutates artifacts, if it replaces full SDD validation, if it only checks the first active feature, or if it requires integration/e2e/golden dependencies.
- **Eval/repair signal**: missing Makefile gate, CLI argument parser rejection, first-feature-only false green, failed Analyze Gate in any active feature, and SDD docs missing default harness command.
- **Implementation**: Add `--all-active` to the gate checker, wire it into `check-all`, document the default gate sweep, and keep individual `--feature --gate` checks for lane-local debugging.
- **Verification**: `uv run pytest tests/architecture/test_harness_structure.py::test_make_check_all_runs_executable_sdd_harness tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_accepts_all_active_features tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_any_failed_active_feature -q`
- **Review owner**: parent
- **Status**: [x]

### Task 183 — Implement gate forwards delegated task drift

- **File(s)**: `scripts/check_sdd_gate.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`
- **Owner**: parent
- **Depends on**: Task 182
- **Touch set**: `scripts/check_sdd_gate.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: `scripts/validate_sdd_artifacts.py`; `scripts/dispatch_sdd_task.py`; `docs/agent-playbook/subagent-handoff-template.md`
- **Failing test first**: `tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_implement_rejects_delegated_artifact_drift` — proves `--gate implement` must fail when a delegated task points at missing subagent handoff/report artifacts.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Implement gate issue selection must include every `task-*` validator issue plus implementation coordination issues such as `tasks-final-verification-duplicated` and `active-touch-conflict`; it must not maintain a narrow stale allowlist that omits subagent handoff/report drift.
- **On-demand context**: `scripts/check_sdd_gate.py`, `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_agent_playbook_contracts.py`, and subagent handoff/report validator issue codes.
- **Kill/defer criteria**: Stop if the implement gate starts reporting clarify/checklist/analyze-only issues, if it masks delegated artifact drift, or if it requires final integration evidence to validate task records.
- **Eval/repair signal**: false-green implement gate, missing subagent handoff/report artifacts, task issue-code drift, and stale gate CLI allowlists.
- **Implementation**: Replace the narrow implement-gate task issue tuple with a predicate that forwards all `task-*` issues plus implementation coordination issues.
- **Verification**: `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_implement_rejects_delegated_artifact_drift -q`
- **Review owner**: parent
- **Status**: [x]

### Task 184 — Gate evidence ignores header-only tables

- **File(s)**: `scripts/check_sdd_gate.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`
- **Owner**: parent
- **Depends on**: Task 183
- **Touch set**: `scripts/check_sdd_gate.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: `scripts/validate_sdd_artifacts.py`; `docs/sdd/_templates/spec-template.md`; `docs/sdd/_templates/plan-template.md`
- **Failing test first**: `tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_header_only_gate_tables` — proves `clarify` gate fails when `## Clarifications` contains only a table header and separator.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Gate table evidence must require at least one non-placeholder body row; the header row and separator row never satisfy `clarify`, `checklist`, or `analyze` gate evidence.
- **On-demand context**: `scripts/check_sdd_gate.py`, `scripts/validate_sdd_artifacts.py`, and gate evidence tests in `tests/architecture/test_agent_playbook_contracts.py`.
- **Kill/defer criteria**: Stop if the parser accepts header-only tables, if it rejects valid body rows, or if it diverges from the full SDD validator's non-placeholder evidence semantics.
- **Eval/repair signal**: header-only false green, placeholder-row false green, and drift between gate CLI and full validator evidence parsing.
- **Implementation**: Change `_has_table_evidence()` to collect table rows, skip the header row, and require a real non-placeholder body row.
- **Verification**: `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_header_only_gate_tables -q`
- **Review owner**: parent
- **Status**: [x]

### Task 185 — Gate evidence shares validator placeholder semantics

- **File(s)**: `scripts/check_sdd_gate.py`, `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`
- **Owner**: parent
- **Depends on**: Task 184
- **Touch set**: `scripts/check_sdd_gate.py`, `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: `scripts/check_sdd_gate.py`; `scripts/validate_sdd_artifacts.py`; `docs/sdd/_templates/spec-template.md`
- **Failing test first**: `tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_placeholder_gate_rows` — proves a `clarify` gate row containing `<pending>` and `YYYY-MM-DD` placeholders fails instead of satisfying gate evidence.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Gate CLI evidence parsing must reuse the full SDD validator's placeholder-cell semantics instead of maintaining a smaller local placeholder list.
- **On-demand context**: `scripts/check_sdd_gate.py`, `scripts/validate_sdd_artifacts.py`, and SDD gate evidence tests.
- **Kill/defer criteria**: Stop if the gate CLI accepts template placeholder rows, if the full validator and gate CLI drift again, or if valid non-placeholder evidence rows are rejected.
- **Eval/repair signal**: placeholder-row false green, duplicated placeholder lists, and drift between `check_sdd_gate.py` and `validate_sdd_artifacts.py`.
- **Implementation**: Expose `is_placeholder_table_cell()` from the full SDD validator and use it inside `check_sdd_gate.py` table evidence parsing.
- **Verification**: `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_placeholder_gate_rows -q`
- **Review owner**: parent
- **Status**: [x]

### Task 186 — Implement gate covers tasks gate compliance

- **File(s)**: `scripts/check_sdd_gate.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`
- **Owner**: parent
- **Depends on**: Task 185
- **Touch set**: `scripts/check_sdd_gate.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: `scripts/validate_sdd_artifacts.py`; `docs/sdd/_templates/tasks-template.md`; `scripts/dispatch_sdd_task.py`
- **Failing test first**: `tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_implement_rejects_missing_task_gate_compliance` — proves `--gate implement` fails when `tasks.md` omits `## Gate Compliance` while retaining structured task records.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Implement gate must forward `missing-gate-section` and `gate-evidence-missing` only for the feature's `tasks.md`, while leaving spec/plan gate section failures to the clarify/checklist/analyze gates.
- **On-demand context**: `scripts/check_sdd_gate.py`, `scripts/validate_sdd_artifacts.py`, `docs/sdd/_templates/tasks-template.md`, and gate CLI architecture tests.
- **Kill/defer criteria**: Stop if implement gate hides missing task gate compliance, if it starts reporting unrelated spec/plan gate issues, or if task records can dispatch without task-level gate evidence.
- **Eval/repair signal**: missing tasks Gate Compliance false green, gate issue over-broadening, and drift between task dispatch readiness and SDD artifact validation.
- **Implementation**: Pass the full `SddIssue` into implement-gate issue selection so `tasks.md` artifact gate issues are forwarded without including spec/plan gate failures.
- **Verification**: `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_implement_rejects_missing_task_gate_compliance -q`
- **Review owner**: parent
- **Status**: [x]

### Task 187 — Analyze gate result statuses are bounded

- **File(s)**: `scripts/check_sdd_gate.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`
- **Owner**: parent
- **Depends on**: Task 186
- **Touch set**: `scripts/check_sdd_gate.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: `scripts/validate_sdd_artifacts.py`; `docs/sdd/_templates/plan-template.md`; `scripts/check_sdd_gate.py`
- **Failing test first**: `tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_unbounded_analyze_status` — proves `--gate analyze` fails when an Analyze Gate result starts with `Warn:` instead of `Pass:` or `Blocked:`.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Analyze gate result rows must use the same bounded result prefixes as the full SDD validator; `Fail:`, `Warn:`, prose, and other non-placeholder values must fail the gate.
- **On-demand context**: `scripts/check_sdd_gate.py`, `scripts/validate_sdd_artifacts.py`, and Analyze Gate tests in `tests/architecture/test_agent_playbook_contracts.py`.
- **Kill/defer criteria**: Stop if Analyze Gate accepts non-bounded statuses, if placeholder rows count as evidence, or if failed/prose result rows are hidden by another passing row.
- **Eval/repair signal**: unbounded Analyze result false green, failed Analyze row accepted by gate CLI, and drift from `plan-analyze-gate-invalid`.
- **Implementation**: Parse Analyze Gate table body rows, skip placeholder rows, and reject every non-placeholder result that does not start with `Pass:` or `Blocked:`.
- **Verification**: `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_unbounded_analyze_status tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_failed_analyze_gate -q`
- **Review owner**: parent
- **Status**: [x]

### Task 188 — SDD sections require heading-line matches

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `scripts/check_sdd_gate.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`
- **Owner**: parent
- **Depends on**: Task 187
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `scripts/check_sdd_gate.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: `docs/sdd/_templates/spec-template.md`; `docs/sdd/_templates/plan-template.md`; `docs/sdd/_templates/tasks-template.md`
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_required_sections_must_be_markdown_heading_lines` and `tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_requires_markdown_heading_lines` — prove backticked `## Clarifications` prose cannot satisfy a missing Markdown heading.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Required section detection and section body extraction must match exact Markdown heading lines, not arbitrary substring tokens inside prose, links, or code spans.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, `scripts/check_sdd_gate.py`, and SDD section/gate architecture tests.
- **Kill/defer criteria**: Stop if line-level heading parsing breaks existing valid SDD records, if gate CLI diverges from the full validator, or if prose tokens can still satisfy section existence.
- **Eval/repair signal**: missing section false green, spec background mis-slicing, gate CLI prose-token false green, and drift between `validate_sdd_artifacts.py` and `check_sdd_gate.py`.
- **Implementation**: Add shared line-level `section_text()` / `has_markdown_section()` helpers to the full validator and reuse `section_text()` from the gate checker.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_required_sections_must_be_markdown_heading_lines tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_requires_markdown_heading_lines -q`
- **Review owner**: parent
- **Status**: [x]

### Task 189 — SDD section parser ignores fenced headings

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`
- **Owner**: parent
- **Depends on**: Task 188
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: `scripts/check_sdd_gate.py`; `docs/sdd/_templates/spec-template.md`; `docs/sdd/_templates/verification-template.md`
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_required_sections_ignore_fenced_heading_tokens` and `tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_ignores_fenced_heading_tokens` — prove fenced `## Clarifications` text cannot satisfy a missing Markdown heading.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Section heading detection and section-body termination must ignore fenced code blocks, so command output, examples, and code snippets cannot create or close SDD sections.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, `scripts/check_sdd_gate.py`, and SDD/gate section parser tests.
- **Kill/defer criteria**: Stop if fenced heading tokens satisfy required sections, if fenced output truncates `verification.md` command evidence, or if gate CLI diverges from validator section parsing.
- **Eval/repair signal**: fenced-heading false green, section-body truncation, and validator/gate CLI parser drift.
- **Implementation**: Track fenced code blocks in the shared section parser when finding headings and when scanning for the next section boundary.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_required_sections_ignore_fenced_heading_tokens tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_ignores_fenced_heading_tokens -q`
- **Review owner**: parent
- **Status**: [x]

### Task 190 — SDD fenced parser covers tilde fences

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`
- **Owner**: parent
- **Depends on**: Task 189
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: `scripts/check_sdd_gate.py`; `docs/sdd/_templates/spec-template.md`; `docs/sdd/_templates/verification-template.md`
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_required_sections_ignore_tilde_fenced_heading_tokens` and `tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_ignores_tilde_fenced_heading_tokens` — prove `~~~` fenced `## Clarifications` text cannot satisfy a missing Markdown heading.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Markdown fence parsing must treat backtick and tilde fences identically for section heading detection and background citation scanning.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, `scripts/check_sdd_gate.py`, and SDD/gate section parser tests.
- **Kill/defer criteria**: Stop if tilde-fenced heading tokens satisfy required sections, if tilde-fenced examples create uncited-background noise, or if gate CLI diverges from validator section parsing.
- **Eval/repair signal**: tilde-fence false green, fenced citation false positive, and validator/gate CLI parser drift.
- **Implementation**: Reuse the shared fence-line helper for citation scanning and expand it to recognize both backtick and tilde Markdown fences.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_required_sections_ignore_tilde_fenced_heading_tokens tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_ignores_tilde_fenced_heading_tokens -q`
- **Review owner**: parent
- **Status**: [x]

### Task 191 — Gate evidence rejects single-cell rows

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `scripts/check_sdd_gate.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`
- **Owner**: parent
- **Depends on**: Task 190
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `scripts/check_sdd_gate.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: `docs/sdd/_templates/spec-template.md`; `docs/sdd/_templates/plan-template.md`; `scripts/check_sdd_gate.py`
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_single_cell_body_rows` and `tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_single_cell_gate_rows` — prove a single non-placeholder table cell cannot satisfy gate evidence.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Gate evidence rows must be table-shaped with at least two non-placeholder cells, and the gate CLI must reuse the validator's row predicate.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, `scripts/check_sdd_gate.py`, and gate evidence architecture tests.
- **Kill/defer criteria**: Stop if single-cell rows satisfy clarify/checklist/analyze evidence, if valid multi-cell body rows are rejected, or if gate CLI table evidence semantics drift from the full validator.
- **Eval/repair signal**: single-cell false green, placeholder false green, and duplicated table-evidence predicates between gate CLI and full validator.
- **Implementation**: Add `is_table_evidence_row()` in the full validator and use it from `check_sdd_gate.py`.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_single_cell_body_rows tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_single_cell_gate_rows -q`
- **Review owner**: parent
- **Status**: [x]

### Task 192 — Gate evidence tables require separators

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `scripts/check_sdd_gate.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`
- **Owner**: parent
- **Depends on**: Task 191
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `scripts/check_sdd_gate.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: `docs/sdd/_templates/spec-template.md`; `docs/sdd/_templates/plan-template.md`; `scripts/check_sdd_gate.py`
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_tables_without_separator_rows` and `tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_gate_tables_without_separator_rows` — prove pipe rows without a Markdown separator cannot satisfy gate evidence.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Gate evidence table parsing must require a header followed by a Markdown separator row before body rows can be considered evidence.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, `scripts/check_sdd_gate.py`, and gate evidence architecture tests.
- **Kill/defer criteria**: Stop if separator-less pipe text satisfies clarify/checklist/analyze evidence, if valid Markdown tables are rejected, or if the gate CLI retains a local parser.
- **Eval/repair signal**: separator-less table false green, valid gate evidence regression, and duplicated table-body parsing between gate CLI and full validator.
- **Implementation**: Add a shared `table_body_rows()` helper in the full validator and use it from `check_sdd_gate.py`.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_tables_without_separator_rows tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_gate_tables_without_separator_rows -q`
- **Review owner**: parent
- **Status**: [x]

### Task 193 — Gate evidence body rows follow separators

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `scripts/check_sdd_gate.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`
- **Owner**: parent
- **Depends on**: Task 192
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `scripts/check_sdd_gate.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: `docs/sdd/_templates/spec-template.md`; `docs/sdd/_templates/plan-template.md`; `scripts/check_sdd_gate.py`
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_body_rows_before_separator` and `tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_body_rows_before_separator` — prove body rows before a separator cannot satisfy gate evidence.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Gate evidence body rows must only be parsed after a header row followed immediately by a Markdown separator row.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, `scripts/check_sdd_gate.py`, and gate evidence architecture tests.
- **Kill/defer criteria**: Stop if pre-separator body rows satisfy clarify/checklist/analyze evidence, if valid Markdown tables are rejected, or if analyze gate result parsing diverges from gate evidence parsing.
- **Eval/repair signal**: pre-separator body false green, separator-less table false green, valid gate evidence regression, and duplicated table-body parsing.
- **Implementation**: Tighten the shared `table_body_rows()` helper to treat the first pipe row as the header, require the second pipe row to be the separator, and return only following non-separator rows.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_body_rows_before_separator tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_body_rows_before_separator -q`
- **Review owner**: parent
- **Status**: [x]

### Task 194 — Gate evidence separators require hyphens

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`
- **Owner**: parent
- **Depends on**: Task 193
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: `scripts/check_sdd_gate.py`; `docs/sdd/_templates/spec-template.md`; `docs/sdd/_templates/plan-template.md`
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_empty_separator_rows` and `tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_empty_separator_rows` — prove empty separator cells cannot satisfy gate evidence.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Every table separator cell must contain at least one hyphen and may only use hyphens plus Markdown alignment colons.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, `scripts/check_sdd_gate.py`, and gate evidence architecture tests.
- **Kill/defer criteria**: Stop if empty or colon-only separator cells satisfy clarify/checklist/analyze evidence, or if valid Markdown alignment separators are rejected.
- **Eval/repair signal**: empty-separator false green, valid aligned-table regression, and drift between gate evidence and analyze gate table parsing.
- **Implementation**: Tighten `_is_table_separator_row()` to validate each separator cell through a hyphen-bearing separator-cell predicate.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_empty_separator_rows tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_empty_separator_rows -q`
- **Review owner**: parent
- **Status**: [x]

### Task 195 — Gate evidence table rows share arity

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`
- **Owner**: parent
- **Depends on**: Task 194
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: `scripts/check_sdd_gate.py`; `docs/sdd/_templates/spec-template.md`; `docs/sdd/_templates/plan-template.md`
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_separator_arity_mismatch`, `tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_body_row_arity_mismatch`, `tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_separator_arity_mismatch`, and `tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_body_row_arity_mismatch` — prove separator/body rows with mismatched column counts cannot satisfy gate evidence.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Gate evidence tables must have one stable arity across header, separator, and every body row before body cells can be evaluated.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, `scripts/check_sdd_gate.py`, and gate evidence architecture tests.
- **Kill/defer criteria**: Stop if mismatched separator/body rows satisfy clarify/checklist/analyze evidence, or if valid equal-arity gate tables are rejected.
- **Eval/repair signal**: separator-arity false green, body-arity false green, valid table regression, and drift between gate evidence and analyze gate table parsing.
- **Implementation**: Have `table_body_rows()` compare separator and body row cell counts against the header cell count before returning evidence rows.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_separator_arity_mismatch tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_body_row_arity_mismatch tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_separator_arity_mismatch tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_body_row_arity_mismatch -q`
- **Review owner**: parent
- **Status**: [x]

### Task 196 — Gate evidence tables are contiguous blocks

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`
- **Owner**: parent
- **Depends on**: Task 195
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: `scripts/check_sdd_gate.py`; `docs/sdd/_templates/spec-template.md`; `docs/sdd/_templates/plan-template.md`
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_non_contiguous_body_rows` and `tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_non_contiguous_body_rows` — prove body rows separated from their header/separator by prose cannot satisfy gate evidence.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Gate evidence rows must come from contiguous Markdown table blocks; parser must not join pipe rows across prose, blank lines, or separate blocks.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, `scripts/check_sdd_gate.py`, and gate evidence architecture tests.
- **Kill/defer criteria**: Stop if non-contiguous pipe rows satisfy clarify/checklist/analyze evidence, or if valid contiguous Markdown tables are rejected.
- **Eval/repair signal**: non-contiguous false green, valid table regression, and drift between gate evidence and analyze gate table parsing.
- **Implementation**: Refactor `table_body_rows()` to split section text into contiguous pipe-row blocks and evaluate each block independently.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_non_contiguous_body_rows tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_non_contiguous_body_rows -q`
- **Review owner**: parent
- **Status**: [x]

### Task 197 — Gate evidence headers are canonical

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `scripts/check_sdd_gate.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`
- **Owner**: parent
- **Depends on**: Task 196
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `scripts/check_sdd_gate.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: `docs/sdd/_templates/spec-template.md`; `docs/sdd/_templates/plan-template.md`; `docs/sdd/_templates/tasks-template.md`
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_wrong_clarification_header` and `tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_wrong_clarification_header` — prove a valid table with generic headers cannot satisfy Clarifications evidence.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Gate evidence tables must match the canonical header tuple for Clarifications, Requirement Checklist, Analyze Gate, and Gate Compliance.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, `scripts/check_sdd_gate.py`, `docs/sdd/_templates/spec-template.md`, `docs/sdd/_templates/plan-template.md`, `docs/sdd/_templates/tasks-template.md`, and gate evidence tests.
- **Kill/defer criteria**: Stop if non-canonical headers satisfy lifecycle gates, if valid template headers are rejected, or if gate CLI keeps a local evidence predicate.
- **Eval/repair signal**: wrong-header false green, template header regression, and drift between full validator and gate CLI evidence semantics.
- **Implementation**: Add a canonical gate header map in the full validator, evaluate gate evidence through `section_has_gate_evidence()`, and use the same helper from `check_sdd_gate.py`.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_wrong_clarification_header tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_wrong_clarification_header -q`
- **Review owner**: parent
- **Status**: [x]

### Task 198 — Analyze results use canonical gate rows

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `scripts/check_sdd_gate.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`
- **Owner**: parent
- **Depends on**: Task 197
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `scripts/check_sdd_gate.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: `docs/sdd/_templates/plan-template.md`; `scripts/check_sdd_gate.py`
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_plan_analyze_gate_ignores_non_canonical_tables` and `tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_ignores_non_canonical_analyze_tables` — prove additional non-canonical tables in `## Analyze Gate` cannot trigger result-status failures.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Analyze result validation must read only rows from the canonical `| Check | Result |` gate table, and the gate CLI must use the same row helper as the full validator.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, `scripts/check_sdd_gate.py`, and Analyze Gate tests.
- **Kill/defer criteria**: Stop if non-canonical tables trigger `plan-analyze-gate-invalid`, if failed canonical rows pass, or if gate CLI keeps a separate broad table scan.
- **Eval/repair signal**: non-canonical table false failure, failed canonical row false green, and validator/gate CLI parser drift.
- **Implementation**: Add `section_gate_table_rows()` in the full validator, use it for Analyze Gate result validation, and switch `check_sdd_gate.py` to the same helper.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_plan_analyze_gate_ignores_non_canonical_tables tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_ignores_non_canonical_analyze_tables -q`
- **Review owner**: parent
- **Status**: [x]

### Task 199 — Analyze invalid-result semantics are shared

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `scripts/check_sdd_gate.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`
- **Owner**: parent
- **Depends on**: Task 198
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `scripts/check_sdd_gate.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: `tests/architecture/test_sdd_artifact_validator.py`; `docs/sdd/_templates/plan-template.md`
- **Failing test first**: `tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_invalid_analyze_result_with_placeholder_check` — proves placeholder text in the check column cannot hide an invalid Analyze result from the gate CLI.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Analyze result invalid-row detection must live in the full validator and be reused by the gate CLI without a local placeholder-cell shortcut.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, `scripts/check_sdd_gate.py`, and Analyze Gate CLI tests.
- **Kill/defer criteria**: Stop if the gate CLI accepts `Warn:` or `Fail:` rows because another cell is placeholder text, if validator and CLI messages drift, or if placeholder result cells stop being ignored as incomplete evidence.
- **Eval/repair signal**: placeholder-check false green, duplicate Analyze result parser, and validator/gate CLI semantic drift.
- **Implementation**: Expose `analyze_gate_invalid_results()` from the full validator, use it in both validator issue generation and `check_sdd_gate.py`, and remove the CLI's local Analyze result parser.
- **Verification**: `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_invalid_analyze_result_with_placeholder_check -q`
- **Review owner**: parent
- **Status**: [x]

### Task 200 — Gate evidence rejects repeated separators

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`
- **Owner**: parent
- **Depends on**: Task 199
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: `scripts/check_sdd_gate.py`; `docs/sdd/_templates/spec-template.md`; `docs/sdd/_templates/plan-template.md`
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_repeated_separator_rows` and `tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_repeated_separator_rows` — prove a second separator row cannot be skipped before accepting later evidence rows.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: A gate evidence table may have exactly one header separator row; separator-shaped rows after the header separator invalidate that table block.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, `scripts/check_sdd_gate.py`, and gate evidence table parser tests.
- **Kill/defer criteria**: Stop if repeated separator rows satisfy gate evidence, if valid single-separator Markdown tables are rejected, or if the gate CLI diverges from the shared parser.
- **Eval/repair signal**: repeated-separator false green, valid-table regression, and validator/gate CLI parser drift.
- **Implementation**: Tighten `_table_block_body_rows()` so any separator-shaped row after the header separator rejects the whole table block instead of being skipped.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_repeated_separator_rows tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_repeated_separator_rows -q`
- **Review owner**: parent
- **Status**: [x]

### Task 201 — Gate evidence rejects repeated headers

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`
- **Owner**: parent
- **Depends on**: Task 200
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: `scripts/check_sdd_gate.py`; `docs/sdd/_templates/spec-template.md`; `docs/sdd/_templates/plan-template.md`
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_repeated_header_rows` and `tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_repeated_header_rows` — prove a copied header row in the body cannot count as evidence.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: A gate evidence table body row must not equal the canonical header tuple for that table.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, `scripts/check_sdd_gate.py`, and gate evidence table parser tests.
- **Kill/defer criteria**: Stop if repeated header rows satisfy gate evidence, if valid evidence rows are rejected, or if the gate CLI diverges from the shared parser.
- **Eval/repair signal**: repeated-header false green, valid-table regression, and validator/gate CLI parser drift.
- **Implementation**: Tighten `_table_block_body_rows()` so a body row equal to the header cells rejects the whole table block.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_repeated_header_rows tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_repeated_header_rows -q`
- **Review owner**: parent
- **Status**: [x]

### Task 202 — Gate evidence rows must close pipes

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`
- **Owner**: parent
- **Depends on**: Task 201
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: `scripts/check_sdd_gate.py`; `docs/sdd/_templates/spec-template.md`; `docs/sdd/_templates/plan-template.md`
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_unclosed_table_rows` and `tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_unclosed_table_rows` — prove a partial pipe row without a trailing `|` cannot count as evidence.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Gate evidence table rows must be closed pipe rows that start and end with `|`.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, `scripts/check_sdd_gate.py`, and gate evidence table parser tests.
- **Kill/defer criteria**: Stop if unclosed pipe rows satisfy gate evidence, if valid closed pipe rows are rejected, or if the gate CLI diverges from the shared parser.
- **Eval/repair signal**: unclosed-row false green, valid-table regression, and validator/gate CLI parser drift.
- **Implementation**: Tighten `table_body_rows()` so only lines that start and end with `|` are part of a table block.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_unclosed_table_rows tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_unclosed_table_rows -q`
- **Review owner**: parent
- **Status**: [x]

### Task 203 — Gate evidence rows use single boundary pipes

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`
- **Owner**: parent
- **Depends on**: Task 202
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: `scripts/check_sdd_gate.py`; `docs/sdd/_templates/spec-template.md`; `docs/sdd/_templates/plan-template.md`
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_doubled_boundary_pipes` and `tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_doubled_boundary_pipes` — prove doubled boundary pipes cannot be stripped into canonical-looking table cells.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Gate evidence table rows must have exactly one boundary pipe at each edge.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, `scripts/check_sdd_gate.py`, and gate evidence table parser tests.
- **Kill/defer criteria**: Stop if doubled boundary pipes satisfy gate evidence, if valid single-boundary rows are rejected, or if the gate CLI diverges from the shared parser.
- **Eval/repair signal**: doubled-boundary false green, valid-table regression, and validator/gate CLI parser drift.
- **Implementation**: Add `_is_table_row_line()` and use it from `table_body_rows()` so only rows with single boundary pipes enter table blocks.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_doubled_boundary_pipes tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_doubled_boundary_pipes -q`
- **Review owner**: parent
- **Status**: [x]

### Task 204 — Gate evidence tables are top-level

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`
- **Owner**: parent
- **Depends on**: Task 203
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: `scripts/check_sdd_gate.py`; `docs/sdd/_templates/spec-template.md`; `docs/sdd/_templates/plan-template.md`
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_indented_table_rows` and `tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_indented_table_rows` — prove indented code-block-style tables cannot count as gate evidence.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Gate evidence table rows must start at column zero; only trailing whitespace may be ignored.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, `scripts/check_sdd_gate.py`, and gate evidence table parser tests.
- **Kill/defer criteria**: Stop if indented table rows satisfy gate evidence, if top-level rows with trailing spaces are rejected, or if the gate CLI diverges from the shared parser.
- **Eval/repair signal**: indented-table false green, top-level table regression, and validator/gate CLI parser drift.
- **Implementation**: Change `table_body_rows()` to preserve leading whitespace and strip only trailing whitespace before table-row detection.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_evidence_rejects_indented_table_rows tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_indented_table_rows -q`
- **Review owner**: parent
- **Status**: [x]

### Task 205 — Clarification approvals use canonical dates

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`
- **Owner**: parent
- **Depends on**: Task 204
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: `scripts/check_sdd_gate.py`; `docs/sdd/_templates/spec-template.md`
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_clarification_gate_evidence_rejects_non_canonical_approval_dates` and `tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_non_canonical_clarification_approval_dates` — prove compact or freeform `Approved at` values cannot satisfy Clarifications gate evidence.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Clarifications gate rows must include an `Approved at` cell in canonical `YYYY-MM-DD` form and parseable as a real date.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, `scripts/check_sdd_gate.py`, and Clarifications gate evidence tests.
- **Kill/defer criteria**: Stop if freeform approval dates satisfy Clarifications evidence, if valid canonical dates are rejected, or if gate CLI evidence semantics diverge from the validator.
- **Eval/repair signal**: non-canonical date false green, valid-date regression, and validator/gate CLI semantic drift.
- **Implementation**: Add heading-specific gate evidence row validation and require Clarifications rows to carry a canonical `YYYY-MM-DD` `Approved at` date through the shared `section_has_gate_evidence()` path.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_clarification_gate_evidence_rejects_non_canonical_approval_dates tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_non_canonical_clarification_approval_dates -q`
- **Review owner**: parent
- **Status**: [x]

### Task 206 — Artifact metadata dates are canonical

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`
- **Owner**: parent
- **Depends on**: Task 205
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: `scripts/regen_sdd_work_index.py`; `docs/sdd/_templates/spec-template.md`; `docs/sdd/_templates/plan-template.md`; `docs/sdd/_templates/tasks-template.md`; `docs/sdd/_templates/verification-template.md`
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_artifact_metadata_dates_require_canonical_real_dates` — proves artifact `Date` and `Approved at` metadata cannot use compact or impossible date values.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Artifact `Date` and `Approved at` fields must be canonical `YYYY-MM-DD` values and parse as real calendar dates before lifecycle metadata is accepted.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, SDD templates, generated SDD index issue-code rows, and SDD artifact validator tests.
- **Kill/defer criteria**: Stop if compact or impossible dates satisfy metadata validation, if placeholder dates stop reporting missing metadata, or if generated lifecycle flags omit the new issue code.
- **Eval/repair signal**: metadata false green, issue-code index drift, and regression in valid current SDD artifacts.
- **Implementation**: Add a `metadata-date-invalid` issue code, validate artifact date metadata through the shared canonical date helper, and reuse the helper from Clarifications gate evidence.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_artifact_metadata_dates_require_canonical_real_dates -q`
- **Review owner**: parent
- **Status**: [x]

### Task 207 — Gate Compliance rows are canonical

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`
- **Owner**: parent
- **Depends on**: Task 206
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: `scripts/check_sdd_gate.py`; `docs/sdd/_templates/tasks-template.md`
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_gate_compliance_requires_all_canonical_gate_rows` and `tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_implement_rejects_incomplete_task_gate_compliance` — prove partial Gate Compliance rows cannot satisfy the validator or implement gate.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `tasks.md` Gate Compliance must include non-placeholder rows for Clarify, Checklist, Analyze, Implement, and Verify before implement readiness is accepted.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, `scripts/check_sdd_gate.py`, `docs/sdd/_templates/tasks-template.md`, and implement gate tests.
- **Kill/defer criteria**: Stop if partial or unknown gate rows satisfy implementation readiness, if valid five-row Gate Compliance tables are rejected, or if the gate CLI diverges from the validator.
- **Eval/repair signal**: partial Gate Compliance false green, fixture drift, and implement gate/validator semantic drift.
- **Implementation**: Add a canonical Gate Compliance gate set and evaluate `## Gate Compliance` evidence through the shared `section_has_gate_evidence()` path.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_compliance_requires_all_canonical_gate_rows tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_implement_rejects_incomplete_task_gate_compliance -q`
- **Review owner**: parent
- **Status**: [x]

### Task 208 — Analyze status rows include evidence

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`
- **Owner**: parent
- **Depends on**: Task 207
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: `scripts/check_sdd_gate.py`; `docs/sdd/_templates/plan-template.md`
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_plan_analyze_gate_rejects_status_without_evidence` and `tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_analyze_status_without_evidence` — prove status-only Analyze results cannot satisfy the validator or analyze gate.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Analyze Gate result cells must start with `Pass:` or `Blocked:` and include non-placeholder evidence after the status token.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, `scripts/check_sdd_gate.py`, `docs/sdd/_templates/plan-template.md`, and Analyze Gate tests.
- **Kill/defer criteria**: Stop if status-only rows satisfy analysis readiness, if valid status-plus-evidence rows are rejected, or if the gate CLI diverges from the validator.
- **Eval/repair signal**: status-only false green, placeholder evidence drift, and validator/gate CLI semantic drift.
- **Implementation**: Add a shared Analyze result predicate used by `analyze_gate_invalid_results()` so both the validator and gate CLI require evidence after the status prefix.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_plan_analyze_gate_rejects_status_without_evidence tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_rejects_analyze_status_without_evidence -q`
- **Review owner**: parent
- **Status**: [x]

### Task 209 — Gate Compliance rows are exact

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`
- **Owner**: parent
- **Depends on**: Task 208
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: `scripts/check_sdd_gate.py`; `docs/sdd/_templates/tasks-template.md`
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_gate_compliance_rejects_duplicate_gate_rows` and `tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_implement_rejects_duplicate_task_gate_compliance` — prove duplicate Gate Compliance rows cannot satisfy the validator or implement gate.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `tasks.md` Gate Compliance rows must exactly match the canonical Clarify, Checklist, Analyze, Implement, Verify sequence with no duplicates, unknown gates, placeholders, or extras.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, `scripts/check_sdd_gate.py`, `docs/sdd/_templates/tasks-template.md`, and implement gate tests.
- **Kill/defer criteria**: Stop if duplicate, reordered, placeholder, or extra Gate Compliance rows satisfy implementation readiness, or if valid canonical tables are rejected.
- **Eval/repair signal**: duplicate Gate Compliance false green, lifecycle order drift, and validator/gate CLI semantic drift.
- **Implementation**: Change Gate Compliance evidence validation from set coverage to exact ordered gate-row matching through the shared `section_has_gate_evidence()` path.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_compliance_rejects_duplicate_gate_rows tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_implement_rejects_duplicate_task_gate_compliance -q`
- **Review owner**: parent
- **Status**: [x]

### Task 210 — Gate Compliance is a single table block

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`
- **Owner**: parent
- **Depends on**: Task 209
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: `scripts/check_sdd_gate.py`; `docs/sdd/_templates/tasks-template.md`
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_gate_compliance_rejects_split_table_blocks` and `tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_implement_rejects_split_task_gate_compliance` — prove multiple Gate Compliance table blocks cannot be stitched into a false canonical lifecycle table.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `tasks.md` Gate Compliance must be exactly one canonical table block whose rows match Clarify, Checklist, Analyze, Implement, Verify in order.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, `scripts/check_sdd_gate.py`, `docs/sdd/_templates/tasks-template.md`, and implement gate tests.
- **Kill/defer criteria**: Stop if split Gate Compliance table blocks satisfy implementation readiness, or if a single canonical table block is rejected.
- **Eval/repair signal**: stitched table-fragment false green, lifecycle evidence contiguity drift, and validator/gate CLI semantic drift.
- **Implementation**: Preserve generic multi-table row collection for other evidence sections, but require Gate Compliance to pass through one valid canonical table block before exact row matching.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_compliance_rejects_split_table_blocks tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_implement_rejects_split_task_gate_compliance -q`
- **Review owner**: parent
- **Status**: [x]

### Task 211 — Verify gate is first-class

- **File(s)**: `scripts/check_sdd_gate.py`, `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_agent_playbook_contracts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/WORKFLOW.md`, `docs/sdd/README.md`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`
- **Owner**: parent
- **Depends on**: Task 210
- **Touch set**: `scripts/check_sdd_gate.py`, `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_agent_playbook_contracts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/WORKFLOW.md`, `docs/sdd/README.md`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: `Makefile`; `docs/sdd/_templates/verification-template.md`
- **Failing test first**: `tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_missing_check_all_evidence`, `tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_incomplete_spec_compliance`, `tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_accepts_verify_gate_with_final_evidence`, and `tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_complete_spec_compliance_rows` — prove final verification is a first-class gate and incomplete Spec compliance rows cannot satisfy completion evidence.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `verify` must be an explicit gate choice, reuse validator completion-evidence rules, and require successful `make check-all` plus complete Spec compliance rows.
- **On-demand context**: `scripts/check_sdd_gate.py`, `scripts/validate_sdd_artifacts.py`, `docs/WORKFLOW.md`, `docs/sdd/README.md`, and verification evidence tests.
- **Kill/defer criteria**: Stop if `verify` is rejected by the CLI parser, if pending Spec compliance rows pass verification, or if default `--all-active` blocks unfinished active features by running verify implicitly.
- **Eval/repair signal**: final-evidence false green, CLI/validator semantic drift, and completion-claim gate gaps.
- **Implementation**: Add a first-class `verify` gate that delegates final-evidence checks to `verify_gate_evidence_issues()` while keeping default all-active sweeps limited to pre-verify gates.
- **Verification**: `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_missing_check_all_evidence tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_incomplete_spec_compliance tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_accepts_verify_gate_with_final_evidence tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_complete_spec_compliance_rows -q`
- **Review owner**: parent
- **Status**: [x]

### Task 212 — Spec compliance rows are required

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`
- **Owner**: parent
- **Depends on**: Task 211
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: `scripts/check_sdd_gate.py`; `docs/sdd/_templates/verification-template.md`
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_spec_compliance_rows` and `tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_empty_spec_compliance` — prove final verification cannot pass with an empty Spec compliance matrix.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `verification.md` Spec compliance must use the canonical `Acceptance criterion | Status | Evidence` table and include at least one evidence row before verify can pass.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, `scripts/check_sdd_gate.py`, and verification evidence tests.
- **Kill/defer criteria**: Stop if a successful `make check-all` block can pass verify while Spec compliance has no canonical evidence rows.
- **Eval/repair signal**: empty completion-matrix false green and final-evidence gate drift.
- **Implementation**: Require `_verified_spec_compliance_issues()` to parse the canonical Spec compliance table and report `verified-incomplete-spec-compliance` when it yields no evidence rows.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_spec_compliance_rows tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_empty_spec_compliance -q`
- **Review owner**: parent
- **Status**: [x]

### Task 213 — Spec compliance covers every AC

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`
- **Owner**: parent
- **Depends on**: Task 212
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: `scripts/check_sdd_gate.py`; `docs/sdd/_templates/verification-template.md`
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_spec_compliance_for_all_acceptance_criteria` and `tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_partial_spec_compliance` — prove final verification cannot pass when `spec.md` declares AC2 but `verification.md` only covers AC1.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `verification.md` Spec compliance row AC numbers must exactly match the acceptance criteria declared in `spec.md`.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, `scripts/check_sdd_gate.py`, and final verification evidence tests.
- **Kill/defer criteria**: Stop if `verify` can pass with missing, extra, duplicate, unnumbered, or reordered AC rows.
- **Eval/repair signal**: partial contract coverage false green and final-evidence gate drift.
- **Implementation**: Compare canonical Spec compliance AC row numbers against `spec.md` acceptance criterion numbers inside the shared verification evidence helper.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_spec_compliance_for_all_acceptance_criteria tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_partial_spec_compliance -q`
- **Review owner**: parent
- **Status**: [x]

### Task 214 — Coverage rows must pass

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`
- **Owner**: parent
- **Depends on**: Task 213
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: `scripts/check_sdd_gate.py`; `docs/sdd/_templates/verification-template.md`
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_passing_coverage_rows` and `tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_pending_coverage` — prove final verification cannot pass with Pending coverage rows even when `make check-all` and Spec compliance pass.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `verification.md` Coverage must use the canonical `metric | value | threshold | status` table and every row status must be complete before verify can pass.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, `scripts/check_sdd_gate.py`, `docs/WORKFLOW.md`, and final verification evidence tests.
- **Kill/defer criteria**: Stop if Pending, failed, missing, or non-canonical coverage rows can satisfy final verification.
- **Eval/repair signal**: coverage-placeholder false green and completion-gate drift.
- **Implementation**: Add `_verified_coverage_issues()` to the shared final-evidence helper and require canonical Coverage rows with complete statuses.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_passing_coverage_rows tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_pending_coverage tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_accepts_verify_gate_with_final_evidence -q`
- **Review owner**: parent
- **Status**: [x]

### Task 215 — E2E golden path must pass

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`
- **Owner**: parent
- **Depends on**: Task 214
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: `scripts/check_sdd_gate.py`; `docs/sdd/_templates/verification-template.md`
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_complete_e2e_golden_path` and `tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_incomplete_e2e_golden_path` — prove final verification cannot pass with unchecked or not-applicable E2E rows.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `verification.md` E2E golden path must include checked rows for `/readyz`, writer visibility, `/api/recent`, `/ws/live`, and testcontainer cleanup; `SKIP_E2E=1` cannot be completion evidence.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, `scripts/check_sdd_gate.py`, `docs/sdd/_templates/verification-template.md`, and final verification evidence tests.
- **Kill/defer criteria**: Stop if unchecked, missing, not-applicable, or skipped E2E evidence can pass final verification.
- **Eval/repair signal**: E2E-golden false green and completion-gate drift.
- **Implementation**: Add `_verified_e2e_issues()` to the shared final-evidence helper and require all canonical E2E runtime signals to be checked.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_complete_e2e_golden_path tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_incomplete_e2e_golden_path tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_accepts_verify_gate_with_final_evidence -q`
- **Review owner**: parent
- **Status**: [x]

### Task 216 — Skipped-test count must be numeric

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`
- **Owner**: parent
- **Depends on**: Task 215
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: `scripts/check_sdd_gate.py`; `docs/sdd/_templates/verification-template.md`
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_numeric_skipped_test_count` and `tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_pending_skipped_count` — prove final verification cannot pass when skipped-test evidence leaves the count as `Pending`.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `verification.md` Skipped tests evidence must include a numeric skipped-test count before any skipped-test table can be accepted by validator or verify gate.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, `scripts/check_sdd_gate.py`, `docs/sdd/_templates/verification-template.md`, and final verification evidence tests.
- **Kill/defer criteria**: Stop if missing, `Pending`, freeform, or non-numeric skipped-test count evidence can pass final verification.
- **Eval/repair signal**: skipped-count false green and completion-gate drift.
- **Implementation**: Require `_verified_issues()` to report `verified-unexplained-skips` when the final verification artifact lacks a numeric skipped-test count, before evaluating skip explanations.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_numeric_skipped_test_count tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_pending_skipped_count -q`
- **Review owner**: parent
- **Status**: [x]

### Task 217 — Skipped-test count is section-local

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`
- **Owner**: parent
- **Depends on**: Task 216
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: `scripts/check_sdd_gate.py`; `docs/sdd/_templates/verification-template.md`
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_skipped_count_inside_skipped_tests_section` and `tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_skipped_count_outside_skipped_section` — prove final verification cannot pass when only stale `Other commands run` output has a numeric skipped-test count.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: skipped-test count and skip explanation rows must be parsed from `## Skipped tests` only, never from historical command output or other verification sections.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, `scripts/check_sdd_gate.py`, `docs/sdd/_templates/verification-template.md`, and final verification evidence tests.
- **Kill/defer criteria**: Stop if a count in `## Other commands run`, fenced historical output, or another non-skipped section can satisfy skipped-test final evidence.
- **Eval/repair signal**: stale skipped-count false green and completion-gate section drift.
- **Implementation**: Scope skipped-test count matching to `_section_text(..., "## Skipped tests")` and validate explanation rows against that same section text.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_skipped_count_inside_skipped_tests_section tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_skipped_count_outside_skipped_section -q`
- **Review owner**: parent
- **Status**: [x]

### Task 218 — Skipped-test explanation table is canonical

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`
- **Owner**: parent
- **Depends on**: Task 217
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: `scripts/check_sdd_gate.py`; `docs/sdd/_templates/verification-template.md`
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_canonical_skipped_tests_table` and `tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_freeform_skipped_table` — prove final verification cannot pass when skipped-test explanations use freeform pipe rows without the canonical header/separator.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: skipped-test explanations must use the canonical `count | reason | acceptable?` table parsed by the shared Markdown table helper.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, `scripts/check_sdd_gate.py`, `docs/sdd/_templates/verification-template.md`, and final verification evidence tests.
- **Kill/defer criteria**: Stop if a headerless, separatorless, wrong-header, or freeform skipped-test table can explain nonzero skipped tests.
- **Eval/repair signal**: skipped-explanation freeform false green and final-evidence table parser drift.
- **Implementation**: Add `SKIPPED_TESTS_HEADER` and validate skipped-test explanation rows with `table_body_rows()` instead of ad hoc pipe-line scanning.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_canonical_skipped_tests_table tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_freeform_skipped_table -q`
- **Review owner**: parent
- **Status**: [x]

### Task 219 — Coverage cells are concrete

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`
- **Owner**: parent
- **Depends on**: Task 218
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: `scripts/check_sdd_gate.py`; `docs/sdd/_templates/verification-template.md`
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_concrete_coverage_values` and `tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_placeholder_coverage_value` — prove final verification cannot pass when Coverage `value` is still `Pending` but `status` says `Pass`.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Coverage evidence must use the canonical `metric | value | threshold | status` table and every canonical cell must be non-placeholder before status completion is considered.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, `scripts/check_sdd_gate.py`, `docs/sdd/_templates/verification-template.md`, and final verification evidence tests.
- **Kill/defer criteria**: Stop if `Pending`, `<pending>`, template, or freeform coverage cells can pass by setting only the status cell to `Pass`.
- **Eval/repair signal**: coverage-value false green and completion-gate evidence drift.
- **Implementation**: Check every canonical Coverage row cell with shared placeholder semantics before evaluating complete status.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_concrete_coverage_values tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_placeholder_coverage_value -q`
- **Review owner**: parent
- **Status**: [x]

### Task 220 — Spec compliance evidence is concrete

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`
- **Owner**: parent
- **Depends on**: Task 219
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: `scripts/check_sdd_gate.py`; `docs/sdd/_templates/verification-template.md`
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_concrete_spec_compliance_evidence` and `tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_placeholder_spec_compliance_evidence` — prove final verification cannot pass when Spec compliance `status` says `Pass` but `Evidence` remains `Pending.`.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: completed Spec compliance rows must have non-placeholder evidence; table placeholder semantics must treat sentence-punctuated placeholders such as `Pending.` as placeholders.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, `scripts/check_sdd_gate.py`, `docs/sdd/_templates/verification-template.md`, and final verification evidence tests.
- **Kill/defer criteria**: Stop if `Pending`, `Pending.`, `<pending>`, or template evidence can pass by setting only the Spec compliance status cell to `Pass`.
- **Eval/repair signal**: spec-evidence false green and completion-gate evidence drift.
- **Implementation**: Reject placeholder Spec compliance evidence cells before command-evidence extraction and normalize table-cell placeholder detection across trailing sentence punctuation.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_concrete_spec_compliance_evidence tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_placeholder_spec_compliance_evidence -q`
- **Review owner**: parent
- **Status**: [x]

### Task 221 — Spec compliance evidence is command-shaped

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`
- **Owner**: parent
- **Depends on**: Task 220
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: `scripts/check_sdd_gate.py`; `docs/sdd/_templates/verification-template.md`
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_command_shaped_spec_compliance_evidence` and `tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_prose_only_spec_compliance_evidence` — prove final verification cannot pass when a complete Spec compliance row has prose-only evidence.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: completed Spec compliance rows must cite at least one command-shaped backticked command so final evidence remains replayable and can be matched against command exit codes.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, `scripts/check_sdd_gate.py`, `docs/sdd/_templates/verification-template.md`, and final verification evidence tests.
- **Kill/defer criteria**: Stop if prose-only, manual-review-only, or narrative compliance evidence can pass final verification without a command-shaped citation.
- **Eval/repair signal**: non-replayable Spec compliance false green and completion-gate evidence drift.
- **Implementation**: Record completed Spec compliance rows that yield no command-shaped evidence references and report `verified-missing-spec-compliance-evidence`.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_command_shaped_spec_compliance_evidence tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_prose_only_spec_compliance_evidence -q`
- **Review owner**: parent
- **Status**: [x]

### Task 222 — E2E evidence ignores fenced examples

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`
- **Owner**: parent
- **Depends on**: Task 221
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: `scripts/check_sdd_gate.py`; `docs/sdd/_templates/verification-template.md`
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_rejects_fenced_e2e_golden_path` and `tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_fenced_e2e_golden_path` — prove final verification cannot pass when the full E2E checklist appears only inside a fenced code block.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `verification.md` E2E golden path evidence must be checked Markdown outside fenced code blocks; example snippets and historical command output cannot satisfy runtime signal evidence.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, `scripts/check_sdd_gate.py`, `docs/sdd/_templates/verification-template.md`, and final verification evidence tests.
- **Kill/defer criteria**: Stop if fenced examples, copied templates, or command-output snippets can satisfy E2E golden-path final evidence.
- **Eval/repair signal**: fenced-E2E false green and completion-gate evidence drift.
- **Implementation**: Strip fenced blocks before evaluating the E2E golden-path section and require the canonical checked runtime signals in the remaining Markdown.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_rejects_fenced_e2e_golden_path tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_fenced_e2e_golden_path -q`
- **Review owner**: parent
- **Status**: [x]

### Task 223 — make check-all evidence uses its own exit code

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`
- **Owner**: parent
- **Depends on**: Task 222
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: `scripts/check_sdd_gate.py`; `docs/sdd/_templates/verification-template.md`
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_make_check_all_own_exit_code_zero` and `tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_failed_check_all_before_helper_success` — prove final verification cannot pass when `$ make check-all` fails before a later helper command exits 0 in the same fenced block.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Final verification must parse the `$ make check-all` command segment and bind its status to that segment's own `exit code`, not to later command output in the same fenced block.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, `scripts/check_sdd_gate.py`, `docs/sdd/_templates/verification-template.md`, and final verification evidence tests.
- **Kill/defer criteria**: Stop if helper commands, repeated command blocks, or later successful exits can satisfy a failed `make check-all` final evidence block.
- **Eval/repair signal**: check-all exit-code false green and completion-gate evidence drift.
- **Implementation**: Segment command transcripts by `$ ...` prompt lines before reading the `make check-all` exit code.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_make_check_all_own_exit_code_zero tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_failed_check_all_before_helper_success -q`
- **Review owner**: parent
- **Status**: [x]

### Task 224 — Task Board exposes repair pressure

- **File(s)**: `scripts/regen_sdd_work_index.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/generated/sdd-work-index.md`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`
- **Owner**: parent
- **Depends on**: Task 223
- **Touch set**: `scripts/regen_sdd_work_index.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/generated/sdd-work-index.md`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`
- **Conflict set**: coordinate with 2026-06-09-agent-playbook-skill-hard-cut for generated SDD index and agent playbook tests.
- **Failing test first**: `tests/architecture/test_agent_playbook_contracts.py::test_sdd_work_index_renders_task_dispatch_board` — proves the generated Task Board must render `Kill/defer criteria` and `Eval/repair signal` columns for every task row.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: The generated Task Board must surface repair pressure directly from existing task fields without becoming a second parser or a prose-only dashboard.
- **On-demand context**: `scripts/regen_sdd_work_index.py`, `scripts/validate_sdd_artifacts.py`, `docs/agent-playbook/factory-operating-model.md`, and the OpenClaw factory-manager transcript notes.
- **Kill/defer criteria**: Stop if generated output hides kill/defer or eval/repair signals, duplicates validation semantics, or drops dispatch/review columns.
- **Eval/repair signal**: stale generated index, missing repair-pressure columns, and review defects from multi-agent handoffs.
- **Implementation**: Add `Kill/defer criteria` and `Eval/repair signal` columns to the generated Task Board rows.
- **Verification**: `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_work_index_renders_task_dispatch_board -q`
- **Review owner**: parent
- **Status**: [x]

### Task 225 — Completion gate has a Make target

- **File(s)**: `Makefile`, `docs/WORKFLOW.md`, `docs/sdd/README.md`, `docs/sdd/_templates/verification-template.md`, `tests/architecture/test_harness_structure.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`
- **Owner**: parent
- **Depends on**: Task 224
- **Touch set**: `Makefile`, `docs/WORKFLOW.md`, `docs/sdd/README.md`, `docs/sdd/_templates/verification-template.md`, `tests/architecture/test_harness_structure.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with 2026-06-09-agent-playbook-skill-hard-cut for shared SDD workflow docs and generated index.
- **Failing test first**: `tests/architecture/test_harness_structure.py::test_makefile_exposes_single_feature_sdd_completion_gate` — proves Makefile and docs expose `make check-sdd-completion FEATURE=<slug>` as the single-feature verify gate.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: The completion gate target must require `FEATURE`, call `scripts/check_sdd_gate.py --feature "$(FEATURE)" --gate verify --check`, and remain distinct from the repo-wide `make check-all` transcript run.
- **On-demand context**: `Makefile`, `docs/WORKFLOW.md`, `docs/sdd/README.md`, `docs/sdd/_templates/verification-template.md`, and `scripts/check_sdd_gate.py`.
- **Kill/defer criteria**: Stop if the target runs all active features, mutates artifacts, hides missing `FEATURE`, or makes `make check-all` the only completion semantics.
- **Eval/repair signal**: completion-doc drift, false completion claims, and failed single-feature verify gate.
- **Implementation**: Add `check-sdd-completion` to Makefile and document it as the single-feature completion gate in workflow docs and the verification template.
- **Verification**: `uv run pytest tests/architecture/test_harness_structure.py::test_makefile_exposes_single_feature_sdd_completion_gate -q`
- **Review owner**: parent
- **Status**: [x]

### Task 226 — Makefile pytest targets reject empty collections

- **File(s)**: `Makefile`, `docs/TESTING.md`, `tests/architecture/test_harness_structure.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`
- **Owner**: parent
- **Depends on**: Task 225
- **Touch set**: `Makefile`, `docs/TESTING.md`, `tests/architecture/test_harness_structure.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with 2026-06-09-agent-playbook-skill-hard-cut for generated SDD index updates.
- **Failing test first**: `tests/architecture/test_harness_structure.py::test_makefile_pytest_targets_do_not_accept_empty_collections` — proves Makefile pytest targets cannot translate pytest empty-collection exit code 5 into success.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Makefile pytest targets must call pytest directly so empty collections fail instead of becoming false green harness or verification evidence.
- **On-demand context**: `Makefile`, `docs/TESTING.md`, `tests/architecture/test_harness_structure.py`, and `docs/sdd/_templates/verification-template.md`.
- **Kill/defer criteria**: Stop if any pytest target keeps exit-code-5 compatibility, hides an empty collection behind shell conditionals, or weakens `make check-all` completion semantics.
- **Eval/repair signal**: empty-collection false green, stale Makefile comments, and completion-gate evidence drift.
- **Implementation**: Remove exit-code-5 success shims from Makefile pytest targets and document that empty collections fail.
- **Verification**: `uv run pytest tests/architecture/test_harness_structure.py::test_makefile_pytest_targets_do_not_accept_empty_collections -q`
- **Review owner**: parent
- **Status**: [x]

### Task 227 — Golden corpus has a dedicated marker

- **File(s)**: `Makefile`, `docs/TESTING.md`, `tests/conftest.py`, `tests/golden/conftest.py`, `tests/architecture/test_harness_structure.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`
- **Owner**: parent
- **Depends on**: Task 226
- **Touch set**: `Makefile`, `docs/TESTING.md`, `tests/conftest.py`, `tests/golden/conftest.py`, `tests/architecture/test_harness_structure.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with 2026-06-09-agent-playbook-skill-hard-cut for generated SDD index updates.
- **Failing test first**: `tests/architecture/test_harness_structure.py::test_golden_lane_uses_dedicated_pytest_marker` — proves the golden corpus lane cannot keep using the service-level e2e marker.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `test-golden` must select `-m golden`, golden corpus collection must auto-mark `pytest.mark.golden`, and service-level `-m e2e` must not select `tests/golden/`.
- **On-demand context**: `Makefile`, `tests/conftest.py`, `tests/golden/conftest.py`, `tests/e2e/conftest.py`, and `docs/TESTING.md`.
- **Kill/defer criteria**: Stop if golden corpus tests remain selected by `-m e2e`, if `test-golden` keeps a marker alias, or if marker registration is split between undocumented compatibility paths.
- **Eval/repair signal**: marker-lane false positives, golden/e2e verification ambiguity, and completion-gate evidence drift.
- **Implementation**: Register the `golden` pytest marker, mark `tests/golden/` with it, switch `test-golden` to `-m golden`, and document the dedicated lane.
- **Verification**: `python -m pytest tests/architecture/test_harness_structure.py::test_golden_lane_uses_dedicated_pytest_marker -q`
- **Review owner**: parent
- **Status**: [x]

### Task 228 — Final runtime lanes fail closed

- **File(s)**: `docs/TESTING.md`, `docs/sdd/_templates/verification-template.md`, `tests/e2e/conftest.py`, `tests/golden/conftest.py`, `tests/architecture/test_harness_structure.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`
- **Owner**: parent
- **Depends on**: Task 227
- **Touch set**: `docs/TESTING.md`, `docs/sdd/_templates/verification-template.md`, `tests/e2e/conftest.py`, `tests/golden/conftest.py`, `tests/architecture/test_harness_structure.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with 2026-06-09-agent-playbook-skill-hard-cut for generated SDD index updates.
- **Failing test first**: `tests/architecture/test_harness_structure.py::test_final_runtime_lanes_do_not_expose_skip_env_switches` — proves E2E/golden runtime lanes and verification templates cannot expose environment skip switches.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: E2E and golden fixtures must fail closed when Docker/PostgreSQL/runtime dependencies are unavailable; final verification templates must not instruct operators to use skip switches.
- **On-demand context**: `tests/e2e/conftest.py`, `tests/golden/conftest.py`, `docs/sdd/_templates/verification-template.md`, and `docs/TESTING.md`.
- **Kill/defer criteria**: Stop if `SKIP_E2E`, `SKIP_GOLDEN`, or "cannot serve as verification evidence" skip language remains in runtime-lane fixtures or the verification template.
- **Eval/repair signal**: skipped-runtime false green, dependency setup failure clarity, and completion-gate evidence drift.
- **Implementation**: Remove E2E/golden environment skip branches and replace template/docs wording with fail-closed runtime-lane guidance.
- **Verification**: `python -m pytest tests/architecture/test_harness_structure.py::test_final_runtime_lanes_do_not_expose_skip_env_switches -q`
- **Review owner**: parent
- **Status**: [x]
