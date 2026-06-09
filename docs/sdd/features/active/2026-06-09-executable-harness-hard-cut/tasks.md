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

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Task 17
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
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

## Final verification

- [ ] `uv run python scripts/validate_sdd_artifacts.py --check`
- [ ] `uv run python scripts/regen_sdd_work_index.py --check`
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
- [ ] `make check-all`
