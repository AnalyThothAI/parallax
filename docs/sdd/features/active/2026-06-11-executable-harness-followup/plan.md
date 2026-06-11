# Plan - Executable Harness Followup

**Status**: In Progress
**Date**: 2026-06-11
**Owning spec**: `docs/sdd/features/active/2026-06-11-executable-harness-followup/spec.md`
**Worktree**: `main`
**Branch**: `main`
**Approved by**: qinghuan
**Approved at**: 2026-06-11

## Pre-flight

- [x] Worktree exists at `main` and `git branch --show-current` matches `main`.
- [x] Prior omnibus record moved to `completed/` as `Superseded`.

## File-level edits

- `scripts/validate_sdd_artifacts.py`: add active feature task-count enforcement.
- `scripts/regen_sdd_work_index.py`: document the new lifecycle issue code in the generated taxonomy.
- `tests/architecture/test_sdd_artifact_validator.py`: add RED coverage for oversized active records.
- `tests/architecture/test_harness_structure.py`: assert workflow/README/template guidance names the active-record bound.
- `docs/WORKFLOW.md`, `docs/sdd/README.md`, `docs/sdd/_templates/tasks-template.md`: document split-or-supersede guidance for active records.
- `docs/sdd/_templates/verification-template.md`: remove stale fixed spec-section anchors from E2E evidence guidance.
- `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`: reject symbolic completion status tokens in final evidence rows.
- Existing SDD verification records: convert table status cells to bounded machine-readable words.
- `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`: reject obsolete SDD lifecycle `--check` flags in active records.
- `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`: reject placeholder final transcript blocks in active verification records.
- `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`: reject numeric active skipped-test counts without successful final `make check-all` evidence.
- `docs/sdd/_templates/verification-template.md`, `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_harness_structure.py`, `tests/architecture/test_sdd_artifact_validator.py`: make template final transcript placeholders fail closed and reject copied placeholders in active records.
- `scripts/build_agent_context_packet.py`, `scripts/dispatch_sdd_task.py`, `tests/architecture/test_agent_playbook_contracts.py`: share dispatchability checks so context packets cannot be generated for completed or dependency-blocked tasks.
- `scripts/build_agent_context_packet.py`, `scripts/dispatch_sdd_task.py`, `docs/agent-playbook/context-packet-template.md`, `docs/agent-playbook/subagent-handoff-template.md`, `docs/agent-playbook/factory-operating-model.md`, `tests/architecture/test_agent_playbook_contracts.py`: emit and document mode-specific edit constraints for subagent context and handoff generation.
- `scripts/agent_mode_constraints.py`, `scripts/build_agent_context_packet.py`, `scripts/dispatch_sdd_task.py`, `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`: share mode constraint text between generators and validator so delegated handoff artifacts cannot omit the matching mode boundary.
- `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`: validate that delegated handoff artifacts embed a Context Packet fenced block with the same `Mode:` and matching mode constraints as the handoff.
- `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`: scope top-level handoff validation outside fenced blocks so embedded Context Packet content cannot satisfy top-level handoff constraints or report-validation commands.
- `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`: require delegated handoff artifacts to include the exact runnable subagent-report validation command instead of a token inventory.
- `scripts/validate_sdd_artifacts.py`, `scripts/build_agent_context_packet.py`, `scripts/dispatch_sdd_task.py`, `scripts/validate_subagent_report.py`, `tests/architecture/test_agent_playbook_contracts.py`: share exact numeric task lookup across context, dispatch, and report-validation CLIs so `--task 1` cannot bind to `Task 10`.
- `scripts/validate_subagent_report.py`, `scripts/subagent_report_contract.py`, `tests/architecture/test_agent_playbook_contracts.py`: require report validation to bind to an active SDD feature/task so weak unbound reports cannot skip task scope, required reading, or verification command checks.
- `scripts/validate_sdd_artifacts.py`, `scripts/build_agent_context_packet.py`, `scripts/dispatch_sdd_task.py`, `scripts/validate_subagent_report.py`, `tests/architecture/test_agent_playbook_contracts.py`: reject noncanonical task selectors such as `--task 01` before they can bind to `Task 1`.
- `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`: reject noncanonical SDD task headings and dependency references such as `Task 01` before they can alias `Task 1`.
- `scripts/subagent_report_contract.py`, `tests/architecture/test_agent_playbook_contracts.py`: require subagent report `Mode:` to be a top-level line outside fenced blocks.
- `scripts/subagent_report_contract.py`, `tests/architecture/test_agent_playbook_contracts.py`: require subagent report section headings to be top-level lines outside fenced blocks.
- `docs/sdd/features/completed/2026-06-09-executable-harness-hard-cut`: retain historical evidence as superseded.
- `docs/sdd/features/active/2026-06-11-executable-harness-followup`: own the follow-up active work.
- `docs/generated/sdd-work-index.md`: regenerate the coordination board.

## Analyze Gate

| Check | Result |
|-------|--------|
| Size bound matches SDD operating model. | Pass: active records are implementation loops, while completed/superseded records retain historical evidence. |

## Acceptance test commands

- AC1: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_active_feature_rejects_unbounded_task_board tests/architecture/test_sdd_artifact_validator.py::test_validator_issue_codes_are_registered_for_generated_lifecycle_index -q`
- AC2: `uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_harness_structure.py::test_sdd_docs_describe_bounded_active_feature_records -q`
- AC3: `uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_harness_structure.py::test_sdd_verification_template_avoids_stale_spec_section_anchors -q`
- AC4: `uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_rejects_symbolic_completion_status_tokens tests/architecture/test_harness_structure.py::test_sdd_verification_template_uses_machine_readable_status_examples -q`
- AC5: `uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_sdd_artifact_validator.py::test_verification_tables_reject_symbolic_status_tokens_before_final_verification -q`
- AC6: `uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_sdd_artifact_validator.py::test_active_records_reject_legacy_sdd_lifecycle_check_flags -q`
- AC7: `uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_sdd_artifact_validator.py::test_active_records_reject_placeholder_final_verification_transcripts -q`
- AC8: `uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_sdd_artifact_validator.py::test_active_records_reject_skipped_count_without_final_evidence -q`
- AC9: `uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_sdd_artifact_validator.py::test_active_records_reject_template_placeholder_final_verification_transcripts tests/architecture/test_harness_structure.py::test_sdd_verification_template_does_not_embed_fake_final_exit_code -q`
- AC10: `uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_agent_playbook_contracts.py::test_context_packet_cli_refuses_completed_task tests/architecture/test_agent_playbook_contracts.py::test_context_packet_cli_refuses_unmet_dependencies -q`
- AC11: `uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_agent_playbook_contracts.py::test_context_packet_cli_emits_mode_constraints tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_dispatch_cli_emits_mode_constraints -q`
- AC12: `uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_handoff_mode_constraints -q`
- AC13: `uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_embedded_context_packet_mode_constraints -q`
- AC14: `uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_top_level_handoff_mode_constraints -q`
- AC15: `uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_exact_report_validation_command -q`
- AC16: `uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_clis_match_exact_task_numbers -q`
- AC17: `uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_requires_task_binding -q`
- AC18: `uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_clis_reject_noncanonical_numeric_selectors -q`
- AC19: `uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_sdd_artifact_validator.py::test_tasks_reject_noncanonical_dependency_references tests/architecture/test_sdd_artifact_validator.py::test_tasks_reject_noncanonical_number_headings -q`
- AC20: `uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_rejects_mode_inside_fenced_block -q`
- AC21: `uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_rejects_sections_inside_fenced_block -q`

## Verification

Verification evidence lives in `docs/sdd/features/active/2026-06-11-executable-harness-followup/verification.md`.
