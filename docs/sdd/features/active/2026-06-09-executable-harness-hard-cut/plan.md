# Plan — Executable Harness Hard Cut

**Status**: In Progress
**Date**: 2026-06-09
**Owning spec**: `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut/spec.md`
**Worktree**: `.worktrees/agent-factory-eval-harness`
**Branch**: `codex/agent-factory-eval-harness`
**Approved by**: qinghuan
**Approved at**: 2026-06-09

## Pre-flight

- [x] Spec is approved by delegated user goal.
- [x] Worktree exists at `.worktrees/agent-factory-eval-harness` and `git branch --show-current` matches `codex/agent-factory-eval-harness`.
- [ ] Baseline `uv run ruff check .` passes.
- [ ] Baseline `uv run pytest` passes or known failures are listed in verification.

Known-failing baseline tests:

- None accepted without verification evidence.

## File-level edits

### `scripts/validate_sdd_artifacts.py`

- Create a pure filesystem validator with `scan_sdd_features(root: Path)`, `validate_sdd_root(root: Path)`, and a `--check` CLI.
- Emit deterministic issue codes for missing gate sections, missing approval metadata, incomplete task fields, false `Verified` evidence, stale generated index, and active touch/conflict overlap.
- Validate `Owning spec` and `Owning plan` links point at the same feature's canonical artifacts before trusting the lifecycle record.
- Validate every `spec.md` acceptance criterion has exactly one matching `plan.md` acceptance test command entry.
- Validate spec and plan AC numbers are unique and contiguous before AC command coverage is trusted.
- Validate plan acceptance test commands are command-shaped, not backticked prose.
- Validate plan acceptance test command bullets are exact AC-numbered machine lines with no trailing prose or side labels.
- Validate feature directory slugs and artifact date metadata so old/freeform planning records cannot pass as current executable SDD.
- Validate clarify, checklist, analyze, and gate-compliance sections have non-placeholder structured evidence rows.
- Validate spec acceptance criteria use executable `WHEN ... THEN ... SHALL ...` structure before plan-command coverage is trusted.
- Validate `Verified` Spec compliance rows by requiring every command-shaped backticked command in completed rows to have exit code 0 evidence in canonical evidence sections.
- Validate Worktree/Branch metadata as machine-readable execution-location state, rejecting template placeholders, prose values, slug mismatches, and cross-artifact disagreement.
- Validate checked plan Pre-flight Worktree/Branch claims against the artifact metadata so stale setup evidence cannot remain checked.
- Validate plan Analyze Gate result cells as machine-statused `Pass:` or `Blocked:` values; freeform `Pass.` or `Fail:` rows are invalid.
- Validate spec Background paragraphs as source-backed claims with existing repo `path:line` citations or external `https://` references.
- Validate task field semantics, not just presence: path-shaped file/touch values, structured conflict rules, command-shaped verification, test-shaped failing-test-first values, and known task status tokens.
- Validate task headings form a unique contiguous `Task 1..N` sequence before dependency or dispatch state is trusted.
- Parse task dependency references and ranges, reject unsupported dependency syntax, and report unresolved task numbers as `task-invalid-dependencies`.
- Reject `[x]` tasks whose declared dependency tasks are not also `[x]`.
- Validate task review evidence: delegated tasks must name a subagent report path and review result, non-delegated tasks must say `not delegated` / `parent-reviewed`, and completed tasks must have explicit `parent-reviewed` or `accepted` review evidence.
- Validate delegated subagent report artifacts by following the report path and running the shared task-bound report contract.
- Validate completed task evidence by requiring each `[x]` task's `Verification` command to appear in `verification.md` with exit code 0.
- Limit completed task evidence to the `## Verification commands` and `## Other commands run` evidence sections.
- Validate machine-token fields strictly so `not delegated` cannot carry prose suffixes.
- Validate delegated subagent handoff artifacts by following the handoff path before dispatch/review.
- Validate delegated subagent handoff artifacts against the owning feature/task/mode so stale handoff prompts cannot pass as current loop evidence.
- Validate delegated subagent reports against the mode granted by the owning handoff artifact, not the mode claimed by the report itself.
- Validate `Factory lane` values as one of the six development-agent lane tokens from the operating model.
- Validate `Superseded` artifact metadata before skipping content-section gates.
- Validate `Superseded` tasks files retain structured `### Task` records instead of legacy checkbox lists.
- Validate all artifacts in a `Superseded` feature point at the same successor record.
- Parse `Verified` completion evidence from the `## Verification commands` fenced block and require final `make check-all` exit code 0 plus explained skipped-test rows.

### `scripts/regen_sdd_work_index.py`

- Replace artifact-only rows with feature-level summaries and a coordination board.
- Reuse the validator metadata rather than duplicating SDD parsing rules.
- Add a task-level dispatch board with per-task status, dispatchability, factory lane, owner, dependencies, touch/conflict scopes, and verification command.
- Mark active tasks with incomplete dependencies as `blocked-by-dependencies`.
- Add subagent report and review result columns, and surface `needs-repair` as dispatch state.

### `scripts/build_agent_context_packet.py`

- Add a pure filesystem CLI that validates SDD records, selects one active feature task, and renders a bounded
  subagent context packet from the task's coordination and agent-loop fields.
- Keep it development-harness only; do not create a product LLM task queue, persistent runtime state, or compatibility
  path for old planning records.

### `scripts/dispatch_sdd_task.py`

- Add a pure filesystem dry-run dispatcher that validates SDD records, selects one active feature task, refuses
  completed, non-dispatchable, or dependency-blocked task statuses, and renders a subagent handoff containing the generated context packet.
- Keep dispatch non-persistent for this slice; no task claiming table, product agent queue, or runtime side effect.
- Include a report contract that routes returned subagent output through `scripts/validate_subagent_report.py`.

### `scripts/validate_subagent_report.py`

- Add a pure filesystem report validator for subagent return packets, with optional `--feature` and `--task` binding.
- Require stable sections for findings, scope adherence, changed files, verification evidence, and remaining risks.
- Reject read-only/review-only reports that list changed files, reject write-allowed reports outside the task touch set or inside the conflict set, reject verification sections without the task's expected command and exit status 0, and reject common secret-bearing fields.

### `tests/architecture/test_agent_playbook_contracts.py`

- Update generated-index assertions from string counters to semantic coordination-board requirements.
- Require the SDD validator to pass as part of the architecture harness.
- Require explicit development-agent factory and eval/repair loop playbook contracts.
- Require the context-packet CLI to build a bounded packet from an active SDD task.
- Require the dry-run dispatch CLI to emit a handoff for in-progress tasks and refuse completed tasks.
- Require the generated SDD index to render task-level dispatch rows from `TaskRecord` metadata.
- Require dependency-blocked tasks to be refused by dispatch and surfaced in the task board.
- Require returned subagent reports to pass a machine-readable report contract before integration.

### `tests/architecture/test_sdd_artifact_validator.py`

- Add fixture tests for invalid task coordination field values and valid explicit `none` dependencies / `not delegated` handoffs.
- Add fixture tests proving old successful `make check-all` snippets outside the canonical verification block do not satisfy `Verified`.

### `tests/architecture/test_test_lane_contracts.py`

- Add taxonomy checks for permanent invariants, migration tripwires, behavior contracts, and generated hygiene.

### `docs/agent-playbook/factory-operating-model.md`

- Codify development-agent lanes as bounded factory lanes, separate from product LLM agents.
- Split deterministic constraints from on-demand context so subagents receive small, precise packets.
- Define parent integrator ownership, maximum lane count, and kill/defer criteria.
- Route subagent handoffs through `scripts/build_agent_context_packet.py` instead of hand-copying template prose.
- Route dispatch prompts through `scripts/dispatch_sdd_task.py` so completed tasks are not handed off again.

### `docs/agent-playbook/eval-repair-loop.md`

- Define trace datasets, review defects, harness failures, token cost, and repair-loop closeout evidence.
- Require verification evidence before any production claim.

### `tests/support/query_contract.py`

- Create a lightweight SQL contract assertion helper that normalizes SQL and supports required tables, forbidden tables, required predicates, forbidden fragments, required locks, and params.

### `tests/unit/domains/macro_intel/test_macro_migration_contract.py`

- Replace the obsolete `concept_history_counts` raw-fact assertion with a projected-row request-path contract using the query-contract helper.

### `src/parallax/domains/macro_intel/repositories/macro_intel_repository.py`

- Update `concept_history_counts` to read `macro_observation_series_rows` for request-path history counts.

### `Makefile`

- Add `uv run python scripts/validate_sdd_artifacts.py --check` and keep `uv run python scripts/regen_sdd_work_index.py --check` in `check-all`.

### `docs/sdd/_templates/*.md`, `docs/WORKFLOW.md`, `docs/sdd/README.md`

- Add machine-readable approval, gate, worktree, touch set, conflict set, analysis, and verification metadata expected by the validator.
- Add factory lane, deterministic constraints, on-demand context, kill/defer criteria, and eval/repair signal fields to task records.
- Add subagent report and review result fields so parent review outcome is task state, not prose.

## PR breakdown

1. **PR 1 — executable SDD harness**: scripts, templates, generated index, architecture tests, Makefile.
2. **PR 2 — SQL contract and macro obsolete test removal**: query helper, macro repository/test update.

This branch implements both slices together because the user requested a thorough hard cut in one pass.

## Rollout order

1. Write failing tests for SDD validator/index/query contract behavior.
2. Implement validator and index generator changes.
3. Regenerate `docs/generated/sdd-work-index.md`.
4. Refactor macro request-path test and implementation.
5. Run focused tests, then broad gates.

## Rollback

This is a development harness hard cut. Rollback is reverting this branch before merge. After merge, false positives should be fixed by adjusting the validator with tests, not by preserving legacy compatibility paths.

## Analyze Gate

| Check | Result |
|-------|--------|
| Spec goals map to plan edits. | Pass: G1-G5 map to script, generated index, tests, query helper, and Makefile edits. |
| Product runtime boundary is untouched. | Pass: no product LLM runtime or queue changes planned. |
| Compatibility paths are removed rather than wrapped. | Pass: no retired planning-lane support planned. |
| Multi-agent coordination is represented as metadata. | Pass: owner/worktree/branch/touch/conflict/review fields are planned. |
| Development-agent loops are separated from product agents. | Pass: factory/eval playbooks explicitly keep product LLM agents outside development-agent lanes. |
| Context packets are executable, not prose-only. | Pass: a new CLI reads active SDD task metadata and emits a bounded handoff packet. |
| Dispatch is dry-run and non-runtime. | Pass: dispatcher emits prompts only and refuses completed tasks without creating durable product state. |
| Task fields are semantically checked. | Pass: validator rejects `none` touch sets, non-command verification, non-test failing-test-first values, and unknown task statuses. |
| Verified evidence is replayable. | Pass: validator reads the canonical command block and validates skipped-test table rows. |
| Task dispatch state is visible. | Pass: generated index includes a `Task Board` with dispatchable/complete/blocked/closed task state. |
| Task dependencies are executable. | Pass: validator checks dependency syntax/resolution and dispatcher/index block incomplete dependencies. |
| Subagent return evidence is executable. | Pass: report validator checks scope adherence, changed files against task scope, verification command/exit code, and secret hygiene. |
| Parent review outcome is task state. | Pass: validator rejects missing/inconsistent review evidence and index exposes review result / needs-repair. |
| Referenced report artifacts are verified. | Pass: SDD validator fails missing or invalid delegated report files. |
| Completed task status is evidenced. | Pass: SDD validator fails `[x]` tasks without matching exit-code evidence. |
| Machine-readable tokens are exact. | Pass: validator rejects `not delegated` values with prose suffixes. |
| Referenced handoff artifacts are verified. | Pass: SDD validator fails missing delegated handoff files. |
| Acceptance commands are executable. | Pass: plan AC command entries must be command-shaped before they count as coverage. |
| Acceptance command lines are exact. | Pass: plan AC command bullets reject trailing prose, ranges, and non-AC labels. |
| Feature identity is machine-valid. | Pass: SDD feature slugs and artifact dates must match the current lane grammar. |
| Gate sections carry evidence. | Pass: required SDD gate sections must contain non-placeholder table rows. |
| Acceptance criteria are executable. | Pass: spec AC lines must use WHEN/THEN/SHALL structure. |
| Verified compliance rows are evidenced. | Pass: command-shaped evidence cited by completed Spec compliance rows must have exit code 0 in canonical evidence sections. |
| Worktree metadata is machine-valid. | Pass: validator rejects placeholder, prose, mismatched, or cross-artifact inconsistent Worktree/Branch fields. |
| Checked Pre-flight setup matches metadata. | Pass: validator rejects checked Worktree/Branch setup claims that disagree with plan metadata. |
| Spec background is source-backed. | Pass: Background claim blocks must cite existing repo `path:line` evidence or external `https://` sources. |
| Delegated handoff artifacts are task-bound. | Pass: validator rejects existing delegated handoff files that name another feature/task/mode or stale report-validation command. |
| Delegated report mode matches handoff mode. | Pass: validator rejects report artifacts whose `Mode:` differs from the owning handoff mode. |
| Factory lanes are bounded. | Pass: validator rejects task `Factory lane` values outside the six operating-model lanes. |
| Analyze gate statuses are bounded. | Pass: validator rejects plan Analyze Gate results that do not begin with `Pass:` or `Blocked:`. |

## Acceptance test commands

- AC1: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_successful_make_check_all_evidence -q`
- AC2: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_tasks_require_filled_coordination_fields -q`
- AC3: `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_work_index_is_generated_and_current -q`
- AC4: `uv run pytest tests/unit/domains/macro_intel/test_macro_migration_contract.py::test_repository_concept_history_counts_reads_projected_rows -q`
- AC5: `make check-all`
- AC6: `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_development_agent_factory_model_is_explicit_and_bounded tests/architecture/test_agent_playbook_contracts.py::test_development_agent_eval_repair_loop_is_defined -q`
- AC7: `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_context_packet_cli -q`
- AC8: `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_dispatch_cli_emits_handoff_for_in_progress_task tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_dispatch_cli_refuses_completed_task -q`
- AC9: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_tasks_reject_invalid_coordination_field_values tests/architecture/test_sdd_artifact_validator.py::test_tasks_allow_explicit_none_dependency_and_not_delegated_handoff -q`
- AC10: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_ignores_old_success_outside_verification_commands tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_skipped_table_to_match_skip_count -q`
- AC11: `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_work_index_renders_task_dispatch_board -q`
- AC12: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_tasks_reject_unresolved_dependencies tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_dispatch_cli_refuses_unmet_dependencies tests/architecture/test_agent_playbook_contracts.py::test_sdd_work_index_renders_task_dispatch_board -q`
- AC13: `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_accepts_evidence_report tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_rejects_unverifiable_or_out_of_scope_report tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_accepts_task_bound_report tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_rejects_task_bound_scope_and_command_drift tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_dispatch_cli_emits_handoff_for_in_progress_task -q`
- AC14: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_review_evidence_fields tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_reject_invalid_review_evidence_values tests/architecture/test_agent_playbook_contracts.py::test_tasks_template_has_parallel_subagent_contract_fields tests/architecture/test_agent_playbook_contracts.py::test_sdd_work_index_renders_task_dispatch_board -q`
- AC15: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_report_artifact tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_validate_report_artifact_against_task tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_accepts_task_bound_report -q`
- AC16: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_complete_tasks_require_matching_verification_evidence tests/architecture/test_agent_playbook_contracts.py::test_context_packet_cli -q`
- AC17: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_non_delegated_handoff_rejects_prose_suffix tests/architecture/test_sdd_artifact_validator.py::test_tasks_allow_explicit_none_dependency_and_not_delegated_handoff tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_report_artifact -q`
- AC18: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_handoff_artifact tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_report_artifact -q`
- AC19: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_feature_rejects_mixed_artifact_statuses -q`
- AC20: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_superseded_feature_requires_machine_readable_successor -q`
- AC21: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_feature_rejects_unexpected_artifact_files -q`
- AC22: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_completed_tasks_reject_incomplete_dependencies -q`
- AC23: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_complete_task_evidence_ignores_commands_outside_evidence_sections -q`
- AC24: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_superseded_feature_requires_approval_metadata -q`
- AC25: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_superseded_feature_requires_structured_tasks -q`
- AC26: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_superseded_feature_requires_one_successor -q`
- AC27: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_complete_tasks_require_review_result_evidence -q`
- AC28: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_tasks_require_unique_contiguous_numbers -q`
- AC29: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_artifact_owning_links_must_point_to_same_feature -q`
- AC30: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_plan_acceptance_commands_must_cover_spec_acceptance_criteria -q`
- AC31: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_acceptance_criteria_and_commands_require_contiguous_numbers -q`
- AC32: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_plan_acceptance_commands_must_be_command_shaped -q`
- AC33: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_plan_acceptance_commands_reject_trailing_prose -q`
- AC34: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_feature_directory_name_and_date_metadata_are_machine_valid -q`
- AC35: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_gate_sections_require_non_placeholder_evidence -q`
- AC36: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_acceptance_criteria_require_when_then_shall_format -q`
- AC37: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_spec_compliance_rows_require_matching_command_evidence -q`
- AC38: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_worktree_branch_metadata_must_be_machine_valid -q`
- AC39: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_spec_background_requires_source_citations -q`
- AC40: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_plan_preflight_worktree_claims_must_match_metadata -q`
- AC41: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_validate_handoff_artifact_against_task -q`
- AC42: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_delegated_report_mode_must_match_handoff_mode -q`
- AC43: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_tasks_reject_invalid_factory_lane_values -q`
- AC44: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_plan_analyze_gate_rejects_failed_results -q`

## Verification

Verification evidence lives in `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut/verification.md`.
