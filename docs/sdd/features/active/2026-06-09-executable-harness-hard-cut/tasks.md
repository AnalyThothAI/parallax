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

- **File(s)**: `src/parallax/domains/token_intel/interfaces.py`, `src/parallax/domains/token_intel/services/token_resolution_refresh.py`, `src/parallax/domains/token_intel/runtime/token_resolution_refresh.py`, `src/parallax/domains/token_intel/runtime/token_intent_rebuild.py`, `src/parallax/app/surfaces/cli/commands/ops.py`, `tests/unit/test_token_resolution_refresh.py`, `tests/architecture/test_src_domain_architecture.py`, `docs/TECH_DEBT.md`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 60
- **Touch set**: `src/parallax/domains/token_intel/interfaces.py`, `src/parallax/domains/token_intel/services/token_resolution_refresh.py`, `src/parallax/domains/token_intel/runtime/token_resolution_refresh.py`, `src/parallax/domains/token_intel/runtime/token_intent_rebuild.py`, `src/parallax/app/surfaces/cli/commands/ops.py`, `tests/unit/test_token_resolution_refresh.py`, `tests/architecture/test_src_domain_architecture.py`, `docs/TECH_DEBT.md`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
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

## Final verification

- [ ] `uv run python scripts/validate_sdd_artifacts.py --check`
- [ ] `uv run python scripts/regen_sdd_work_index.py --check`
- [ ] `uv run python scripts/regen_cli_help.py --check`
- [ ] `uv run pytest tests/architecture/test_sdd_artifact_validator.py tests/architecture/test_agent_playbook_contracts.py tests/architecture/test_test_lane_contracts.py -q`
- [ ] `uv run pytest tests/unit/domains/macro_intel/test_macro_migration_contract.py -q`
- [ ] `uv run pytest tests/architecture/test_agent_playbook_contracts.py tests/architecture/test_sdd_artifact_validator.py -q`
- [ ] `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_context_packet_cli -q`
- [ ] `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_dispatch_cli_emits_handoff_for_in_progress_task tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_dispatch_cli_refuses_completed_task -q`
- [ ] `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_tasks_reject_invalid_coordination_field_values tests/architecture/test_sdd_artifact_validator.py::test_tasks_allow_explicit_none_dependency_and_not_delegated_handoff -q`
- [ ] `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_ignores_old_success_outside_verification_commands tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_skipped_table_to_match_skip_count -q`
- [ ] `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_work_index_renders_task_dispatch_board -q`
- [ ] `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_tasks_reject_unresolved_dependencies tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_dispatch_cli_refuses_unmet_dependencies tests/architecture/test_agent_playbook_contracts.py::test_sdd_work_index_renders_task_dispatch_board -q`
- [ ] `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_accepts_evidence_report tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_rejects_unverifiable_or_out_of_scope_report tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_accepts_task_bound_report tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_rejects_task_bound_scope_and_command_drift tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_dispatch_cli_emits_handoff_for_in_progress_task -q`
- [ ] `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_review_evidence_fields tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_reject_invalid_review_evidence_values tests/architecture/test_agent_playbook_contracts.py::test_tasks_template_has_parallel_subagent_contract_fields tests/architecture/test_agent_playbook_contracts.py::test_sdd_work_index_renders_task_dispatch_board -q`
- [ ] `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_report_artifact tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_validate_report_artifact_against_task tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_accepts_task_bound_report -q`
- [ ] `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_complete_tasks_require_matching_verification_evidence tests/architecture/test_agent_playbook_contracts.py::test_context_packet_cli -q`
- [ ] `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_non_delegated_handoff_rejects_prose_suffix tests/architecture/test_sdd_artifact_validator.py::test_tasks_allow_explicit_none_dependency_and_not_delegated_handoff tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_report_artifact -q`
- [ ] `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_handoff_artifact tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_report_artifact -q`
- [ ] `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_feature_rejects_mixed_artifact_statuses -q`
- [ ] `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_superseded_feature_requires_machine_readable_successor -q`
- [ ] `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_feature_rejects_unexpected_artifact_files -q`
- [ ] `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_completed_tasks_reject_incomplete_dependencies -q`
- [ ] `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_complete_task_evidence_ignores_commands_outside_evidence_sections -q`
- [ ] `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_superseded_feature_requires_approval_metadata -q`
- [ ] `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_superseded_feature_requires_structured_tasks -q`
- [ ] `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_superseded_feature_requires_one_successor -q`
- [ ] `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_complete_tasks_require_review_result_evidence -q`
- [ ] `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_tasks_require_unique_contiguous_numbers -q`
- [ ] `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_artifact_owning_links_must_point_to_same_feature -q`
- [ ] `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_plan_acceptance_commands_must_cover_spec_acceptance_criteria -q`
- [ ] `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_acceptance_criteria_and_commands_require_contiguous_numbers -q`
- [ ] `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_plan_acceptance_commands_must_be_command_shaped -q`
- [ ] `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_plan_acceptance_commands_reject_trailing_prose -q`
- [ ] `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_feature_directory_name_and_date_metadata_are_machine_valid -q`
- [ ] `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_sections_require_non_placeholder_evidence -q`
- [ ] `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_acceptance_criteria_require_when_then_shall_format -q`
- [ ] `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_spec_compliance_rows_require_matching_command_evidence -q`
- [ ] `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_worktree_branch_metadata_must_be_machine_valid -q`
- [ ] `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_spec_background_requires_source_citations -q`
- [ ] `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_plan_preflight_worktree_claims_must_match_metadata -q`
- [ ] `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_validate_handoff_artifact_against_task -q`
- [ ] `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_delegated_report_mode_must_match_handoff_mode -q`
- [ ] `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_tasks_reject_invalid_factory_lane_values -q`
- [ ] `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_plan_analyze_gate_rejects_failed_results -q`
- [ ] `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_complete_tasks_require_failing_test_reference_evidence -q`
- [ ] `uv run pytest tests/architecture/test_harness_structure.py::test_make_check_all_checks_cli_help_snapshot -q`
- [ ] `uv run pytest tests/architecture/test_public_contracts_doc_alignment.py -q`
- [ ] `uv run pytest tests/architecture/test_harness_structure.py::test_generated_readme_source_map_points_to_existing_paths -q`
- [ ] `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_active_touch_sets_reject_nested_or_misdirected_coordination -q`
- [ ] `cd web && npm run test -- tests/architecture/frontendDocContract.test.ts`
- [ ] `cd web && npm run test -- tests/architecture/featureBoundaries.test.ts`
- [ ] `cd web && npm run test -- tests/architecture/frontendDataOwnership.test.ts`
- [ ] `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_agent_router_frontend_guardrails_match_css_harness -q`
- [ ] `cd web && npm run test -- tests/architecture/frontendDocContract.test.ts`
- [ ] `uv run pytest tests/architecture/test_harness_structure.py::test_architecture_doc_test_references_are_path_qualified_and_existing -q`
- [ ] `uv run pytest tests/architecture/test_harness_structure.py::test_architecture_module_map_links_every_domain_architecture_doc -q`
- [ ] `uv run pytest tests/architecture/test_test_lane_contracts.py::test_architecture_tests_declare_harness_taxonomy -q`
- [ ] `uv run pytest tests/architecture/test_harness_structure.py::test_open_tech_debt_references_current_source_and_test_paths -q`
- [ ] `uv run pytest tests/architecture/test_harness_structure.py::test_rule_ownership tests/architecture/test_harness_structure.py::test_routers_have_no_governance_phrases -q`
- [ ] `uv run pytest tests/architecture/test_src_domain_architecture.py::test_domain_types_do_not_import_upward_layers -q`
- [ ] `uv run pytest tests/architecture/test_src_domain_architecture.py::test_domain_interfaces_do_not_import_runtime_modules -q`
- [ ] `uv run pytest tests/architecture/test_harness_structure.py::test_open_tech_debt_duplicate_symbol_claims_match_current_sources -q`
- [ ] `uv run pytest tests/architecture/test_harness_structure.py::test_generated_ws_protocol_documents_current_type_literals -q`
- [ ] `uv run pytest tests/architecture/test_harness_structure.py::test_make_check_all_checks_ws_protocol_snapshot -q`
- [ ] `uv run pytest tests/architecture/test_harness_structure.py::test_make_check_all_checks_score_versions_snapshot -q`
- [ ] `uv run pytest tests/architecture/test_harness_structure.py::test_make_check_all_checks_non_db_generated_snapshots -q`
- [ ] `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_requires_task_classification_and_required_reading_evidence tests/architecture/test_agent_playbook_contracts.py::test_subagent_handoff_templates_define_context_and_conflict_contracts -q`
- [ ] `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_spec_background_rejects_stale_local_citation_lines -q`
- [ ] `uv run pytest tests/architecture/test_runtime_worker_constraint_hard_cut.py::test_every_registered_worker_has_runtime_constraint_classification -q`
- [ ] `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_architecture_tests_do_not_import_peer_architecture_tests_as_sources -q`
- [ ] `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_exposes_owned_tables_as_source_contract -q`
- [ ] `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_exposes_read_model_writer_mapping -q`
- [ ] `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_read_model_writers -q`
- [ ] `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_unowned_read_model_identities -q`
- [ ] `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_read_model_identity_entries -q`
- [ ] `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_table_declarations -q`
- [ ] `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_read_model_identity_columns tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_run_generation_identity_and_skips_unchanged -q`
- [ ] `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_empty_read_model_identity_columns -q`
- [ ] `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_table_declarations -q`
- [ ] `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_read_model_identity_columns tests/architecture/test_worker_manifest_static_contracts.py::test_current_read_model_publisher_rejects_run_generation_identity_and_skips_unchanged -q`
- [ ] `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_read_model_identity_tables -q`
- [ ] `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_dirty_consumers_without_dirty_targets -q`
- [ ] `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_leased_consumers_without_queue_depth -q`
- [ ] `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_provider_schedulers_without_provider_io -q`
- [ ] `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_unowned_queue_depth_tables -q`
- [ ] `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_ledgers_on_non_side_effect_workers -q`
- [ ] `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_wake_channels -q`
- [ ] `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_wake_channels -q`
- [ ] `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_advisory_lock_keys -q`
- [ ] `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_advisory_lock_keys -q`
- [ ] `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_identity_fields -q`
- [ ] `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_idempotency_evidence -q`
- [ ] `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_empty_input_contracts -q`
- [ ] `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_input_contracts -q`
- [ ] `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_empty_ordering_keys -q`
- [ ] `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_blank_ordering_keys -q`
- [ ] `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_ordering_keys -q`
- [ ] `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_input_contracts -q`
- [ ] `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_idempotency_evidence -q`
- [ ] `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_duplicate_worker_classes -q`
- [ ] `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_negative_start_priorities -q`
- [ ] `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_non_integer_start_priorities -q`
- [ ] `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_missing_factory_modules -q`
- [ ] `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_missing_worker_class_modules -q`
- [ ] `uv run pytest tests/architecture/test_worker_inventory_contract.py::test_worker_manifest_validation_rejects_missing_worker_class_names -q`
- [ ] `make check-all`
