# Tasks - Executable Harness Followup

**Status**: Superseded
**Superseded by**: `docs/ARCHITECTURE.md`
**Owning plan**: `docs/sdd/features/completed/2026-06-11-executable-harness-followup/plan.md`
**Worktree**: `main`
**Branch**: `main`
**Approved by**: qinghuan
**Approved at**: 2026-06-11

## Gate Compliance

| Gate | Evidence |
|------|----------|
| Clarify | Spec contains approved clarification for superseding the omnibus record. |
| Checklist | Spec records the active-record size bound requirement. |
| Analyze | Plan Analyze Gate records why active records should remain bounded. |
| Implement | Tasks 1-23 implement the validator, migration, documentation contract, stale-template cleanup, machine-readable verification status tokens, active lifecycle command hard cut, active placeholder final-evidence rejection, active skipped-test accounting bound, fail-closed final-evidence templates, dispatch-bound context packets, generated subagent mode constraints, validator-enforced handoff mode constraints, embedded context-packet mode constraints, top-level handoff validation scope, exact report validation command enforcement, exact task-number selection, task-bound report validation, canonical task selector parsing, canonical SDD task identity parsing, top-level report mode binding, top-level report section binding, top-level report claim binding, and singular report mode binding. |
| Verify | Verification artifact captures RED/GREEN command output. |

## Tasks

### Task 1 - Bound active SDD task boards

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/completed/2026-06-11-executable-harness-followup`, `docs/sdd/features/completed/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: none
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/completed/2026-06-11-executable-harness-followup`, `docs/sdd/features/completed/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with 2026-06-09-agent-playbook-skill-hard-cut for shared generated SDD index updates; coordinate with 2026-07-21-signal-pulse-hard-cut for shared generated SDD index.
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_active_feature_rejects_unbounded_task_board` — proves oversized active task boards fail validation.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Active SDD records may contain at most 40 structured tasks; larger work continues through a successor feature instead of an omnibus active ledger.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, `docs/sdd/features/completed/2026-06-09-executable-harness-hard-cut`, SDD generated index.
- **Kill/defer criteria**: Stop if current active work cannot be split without losing historical evidence.
- **Eval/repair signal**: `active-feature-too-large`, stale active index rows, or successor metadata drift.
- **Implementation**: Add validator enforcement, move the omnibus feature to completed as Superseded, and create this bounded active successor.
- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_active_feature_rejects_unbounded_task_board tests/architecture/test_sdd_artifact_validator.py::test_validator_issue_codes_are_registered_for_generated_lifecycle_index -q`
- **Review owner**: parent
- **Status**: [x]

### Task 2 - Document bounded active records

- **File(s)**: `docs/WORKFLOW.md`, `docs/sdd/README.md`, `docs/sdd/_templates/tasks-template.md`, `tests/architecture/test_harness_structure.py`, `docs/sdd/features/completed/2026-06-11-executable-harness-followup`
- **Owner**: parent
- **Depends on**: Task 1
- **Touch set**: `docs/WORKFLOW.md`, `docs/sdd/README.md`, `docs/sdd/_templates/tasks-template.md`, `tests/architecture/test_harness_structure.py`, `docs/sdd/features/completed/2026-06-11-executable-harness-followup`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with 2026-06-09-agent-playbook-skill-hard-cut for shared SDD workflow docs and generated index updates.
- **Failing test first**: `tests/architecture/test_harness_structure.py::test_sdd_docs_describe_bounded_active_feature_records` — proves workflow docs and templates cannot drift from the active task-board bound.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Docs/contracts
- **Deterministic constraints**: `docs/WORKFLOW.md`, README, and task template must name `40 structured tasks`, `active-feature-too-large`, and `split or supersede`.
- **On-demand context**: `docs/WORKFLOW.md`, `docs/sdd/README.md`, `docs/sdd/_templates/tasks-template.md`, `scripts/validate_sdd_artifacts.py`.
- **Kill/defer criteria**: Stop if the validator limit is intentionally hidden from operator-facing SDD docs.
- **Eval/repair signal**: docs/template drift, stale active-record guidance, or `test_sdd_docs_describe_bounded_active_feature_records` failure.
- **Implementation**: Add SDD workflow guidance for bounded active records and a harness test that imports the validator limit.
- **Verification**: `uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_harness_structure.py::test_sdd_docs_describe_bounded_active_feature_records -q`
- **Review owner**: parent
- **Status**: [x]

### Task 3 - Remove stale verification-template section anchors

- **File(s)**: `docs/sdd/_templates/verification-template.md`, `tests/architecture/test_harness_structure.py`, `docs/sdd/features/completed/2026-06-11-executable-harness-followup`
- **Owner**: parent
- **Depends on**: Task 2
- **Touch set**: `docs/sdd/_templates/verification-template.md`, `tests/architecture/test_harness_structure.py`, `docs/sdd/features/completed/2026-06-11-executable-harness-followup`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with 2026-06-09-agent-playbook-skill-hard-cut for shared SDD template or generated index updates.
- **Failing test first**: `tests/architecture/test_harness_structure.py::test_sdd_verification_template_avoids_stale_spec_section_anchors` — proves verification templates cannot teach historical fixed spec-section anchors.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Docs/contracts
- **Deterministic constraints**: Verification template E2E guidance must reference the current feature spec, must not mention `§6.4`, and must retain the single-feature completion gate command.
- **On-demand context**: `docs/sdd/_templates/verification-template.md`, `docs/WORKFLOW.md`, `tests/architecture/test_harness_structure.py`.
- **Kill/defer criteria**: Stop if E2E evidence is intentionally tied to a fixed spec section by a current canonical doc.
- **Eval/repair signal**: stale section anchors, stale template instructions, or `test_sdd_verification_template_avoids_stale_spec_section_anchors` failure.
- **Implementation**: Replace the fixed `spec §6.4` wording with current-feature-spec guidance and add a harness test for the template contract.
- **Verification**: `uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_harness_structure.py::test_sdd_verification_template_avoids_stale_spec_section_anchors -q`
- **Review owner**: parent
- **Status**: [x]

### Task 4 - Require machine-readable final evidence status tokens

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `docs/sdd/_templates/verification-template.md`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_harness_structure.py`, `docs/sdd/features/completed/2026-06-11-executable-harness-followup`
- **Owner**: parent
- **Depends on**: Task 3
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `docs/sdd/_templates/verification-template.md`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_harness_structure.py`, `docs/sdd/features/completed/2026-06-11-executable-harness-followup`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with 2026-06-09-agent-playbook-skill-hard-cut for shared SDD template, validator, or generated index updates.
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_rejects_symbolic_completion_status_tokens` — proves symbolic completion status tokens fail final verification.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Final evidence status cells use machine-readable status words; `✅` and `❌` are not accepted or taught as completion status examples.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, `docs/sdd/_templates/verification-template.md`, `tests/architecture/test_sdd_artifact_validator.py`.
- **Kill/defer criteria**: Stop if current Verified records require symbolic status compatibility.
- **Eval/repair signal**: symbolic final status tokens, stale emoji template examples, or `test_verified_feature_rejects_symbolic_completion_status_tokens` failure.
- **Implementation**: Remove checkmark status acceptance from the validator and update verification-template examples to `Pass`/`Fail` with ASCII thresholds.
- **Verification**: `uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_rejects_symbolic_completion_status_tokens tests/architecture/test_harness_structure.py::test_sdd_verification_template_uses_machine_readable_status_examples -q`
- **Review owner**: parent
- **Status**: [x]

### Task 5 - Enforce machine-readable verification table statuses lifecycle-wide

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/active/2026-06-09-agent-playbook-skill-hard-cut/verification.md`, `docs/sdd/features/completed/2026-06-09-executable-harness-hard-cut/verification.md`, `docs/sdd/features/completed/2026-06-09-macro-intel-redesign/verification.md`, `docs/sdd/features/completed/2026-06-11-executable-harness-followup`
- **Owner**: parent
- **Depends on**: Task 4
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/active/2026-06-09-agent-playbook-skill-hard-cut/verification.md`, `docs/sdd/features/completed/2026-06-09-executable-harness-hard-cut/verification.md`, `docs/sdd/features/completed/2026-06-09-macro-intel-redesign/verification.md`, `docs/sdd/features/completed/2026-06-11-executable-harness-followup`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with 2026-06-09-agent-playbook-skill-hard-cut for shared active verification and generated index updates.
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_verification_tables_reject_symbolic_status_tokens_before_final_verification` — proves non-final verification tables reject symbolic status cells.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `verification.md` Spec compliance and Coverage status cells must use bounded machine-readable status words in active, superseded, and verified records.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, existing SDD verification records, generated issue taxonomy.
- **Kill/defer criteria**: Stop if current records require symbolic status cells as canonical evidence.
- **Eval/repair signal**: `verification-status-token-invalid`, symbolic table status cells, or stale generated issue taxonomy.
- **Implementation**: Add a lifecycle-wide verification status-token validator, register the issue code, and convert existing SDD verification status cells to machine-readable words.
- **Verification**: `uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_sdd_artifact_validator.py::test_verification_tables_reject_symbolic_status_tokens_before_final_verification -q`
- **Review owner**: parent
- **Status**: [x]

### Task 6 - Reject obsolete SDD lifecycle --check flags in active records

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/active/2026-06-09-agent-playbook-skill-hard-cut/tasks.md`, `docs/sdd/features/active/2026-06-09-agent-playbook-skill-hard-cut/verification.md`, `docs/sdd/features/completed/2026-06-11-executable-harness-followup`
- **Owner**: parent
- **Depends on**: Task 5
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/active/2026-06-09-agent-playbook-skill-hard-cut`, `docs/sdd/features/completed/2026-06-11-executable-harness-followup`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with 2026-06-09-agent-playbook-skill-hard-cut for shared active lifecycle command cleanup and generated index updates.
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_active_records_reject_legacy_sdd_lifecycle_check_flags` — proves active records reject obsolete SDD lifecycle `--check` flags.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Active records may use `scripts/regen_sdd_work_index.py --check` for generated freshness, but may not advertise `--check` on `scripts/validate_sdd_artifacts.py` or `scripts/check_sdd_gate.py`.
- **On-demand context**: active SDD records, SDD lifecycle CLIs, generated issue taxonomy.
- **Kill/defer criteria**: Stop if an active record legitimately requires old report-only lifecycle flags.
- **Eval/repair signal**: `active-sdd-lifecycle-check-flag-invalid`, active records with stale lifecycle commands, or stale generated issue taxonomy.
- **Implementation**: Add an active-record lifecycle-command validator, register the issue code, and update active agent-playbook SDD evidence to use the current fail-closed validator command.
- **Verification**: `uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_sdd_artifact_validator.py::test_active_records_reject_legacy_sdd_lifecycle_check_flags -q`
- **Review owner**: parent
- **Status**: [x]

### Task 7 - Reject placeholder final transcripts in active verification records

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/active/2026-06-09-agent-playbook-skill-hard-cut/verification.md`, `docs/sdd/features/completed/2026-06-11-executable-harness-followup`
- **Owner**: parent
- **Depends on**: Task 6
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/active/2026-06-09-agent-playbook-skill-hard-cut/verification.md`, `docs/sdd/features/completed/2026-06-11-executable-harness-followup`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with 2026-06-09-agent-playbook-skill-hard-cut for shared active verification cleanup and generated index updates.
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_active_records_reject_placeholder_final_verification_transcripts` — proves active records reject placeholder final command transcripts.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Active `verification.md` records may state that final completion evidence is not yet available, but must not contain placeholder `$ make check-all` transcripts or `exit code: pending`.
- **On-demand context**: active SDD verification records, `scripts/validate_sdd_artifacts.py`, generated issue taxonomy.
- **Kill/defer criteria**: Stop if active records need placeholder command output to satisfy required sections.
- **Eval/repair signal**: `active-placeholder-final-evidence`, placeholder final transcript text, or stale generated issue taxonomy.
- **Implementation**: Add an active-record placeholder-final-evidence validator, register the issue code, and replace the active agent-playbook placeholder transcript with explicit non-final prose.
- **Verification**: `uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_sdd_artifact_validator.py::test_active_records_reject_placeholder_final_verification_transcripts -q`
- **Review owner**: parent
- **Status**: [x]

### Task 8 - Bind active skipped-test accounting to final evidence

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/active/2026-06-09-agent-playbook-skill-hard-cut/verification.md`, `docs/sdd/features/completed/2026-06-11-executable-harness-followup`
- **Owner**: parent
- **Depends on**: Task 7
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/active/2026-06-09-agent-playbook-skill-hard-cut/verification.md`, `docs/sdd/features/completed/2026-06-11-executable-harness-followup`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with 2026-06-09-agent-playbook-skill-hard-cut for shared active verification cleanup and generated index updates.
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_active_records_reject_skipped_count_without_final_evidence` - proves active records reject numeric skipped-test counts without final evidence.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Active `verification.md` records may say skipped-test accounting is not final yet, but numeric run-above counts require successful final `make check-all` evidence.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, active SDD verification records, generated issue taxonomy.
- **Kill/defer criteria**: Stop if active records intentionally need zero-skip completion claims before final evidence exists.
- **Eval/repair signal**: `active-skipped-count-without-final-evidence`, numeric active skipped-test counts without final evidence, or stale generated issue taxonomy.
- **Implementation**: Add active skipped-test accounting validation, register the issue code, and replace active non-final zero-skip claims with explicit non-final prose.
- **Verification**: `uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_sdd_artifact_validator.py::test_active_records_reject_skipped_count_without_final_evidence -q`
- **Review owner**: parent
- **Status**: [x]

### Task 9 - Make verification transcript placeholders fail closed

- **File(s)**: `docs/sdd/_templates/verification-template.md`, `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_harness_structure.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/completed/2026-06-11-executable-harness-followup`
- **Owner**: parent
- **Depends on**: Task 8
- **Touch set**: `docs/sdd/_templates/verification-template.md`, `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_harness_structure.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/completed/2026-06-11-executable-harness-followup`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with 2026-06-09-agent-playbook-skill-hard-cut for shared SDD template and generated index updates.
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_active_records_reject_template_placeholder_final_verification_transcripts` and `tests/architecture/test_harness_structure.py::test_sdd_verification_template_does_not_embed_fake_final_exit_code` - prove copied template transcripts and fake template exit codes fail.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Verification templates may show where final evidence belongs, but must not include a success-shaped final transcript placeholder.
- **On-demand context**: `docs/sdd/_templates/verification-template.md`, `scripts/validate_sdd_artifacts.py`, SDD completion gate docs.
- **Kill/defer criteria**: Stop if operators intentionally need templates that pass when copied unchanged.
- **Eval/repair signal**: copied `<paste full stdout/stderr here>` transcript placeholders, fake template `exit code: 0`, or stale generated index rows.
- **Implementation**: Add the template placeholder to active placeholder-final-evidence validation and change the verification template command block to use a non-success exit placeholder.
- **Verification**: `uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_sdd_artifact_validator.py::test_active_records_reject_template_placeholder_final_verification_transcripts tests/architecture/test_harness_structure.py::test_sdd_verification_template_does_not_embed_fake_final_exit_code -q`
- **Review owner**: parent
- **Status**: [x]

### Task 10 - Bind context packet generation to dispatchability

- **File(s)**: `scripts/build_agent_context_packet.py`, `scripts/dispatch_sdd_task.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/completed/2026-06-11-executable-harness-followup`
- **Owner**: parent
- **Depends on**: Task 9
- **Touch set**: `scripts/build_agent_context_packet.py`, `scripts/dispatch_sdd_task.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/completed/2026-06-11-executable-harness-followup`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with 2026-06-09-agent-playbook-skill-hard-cut for shared agent playbook CLI tests and generated index updates.
- **Failing test first**: `tests/architecture/test_agent_playbook_contracts.py::test_context_packet_cli_refuses_completed_task` and `tests/architecture/test_agent_playbook_contracts.py::test_context_packet_cli_refuses_unmet_dependencies` - prove context packets cannot be generated for non-dispatchable tasks.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Context packets and subagent handoffs must share one dispatchability rule: `[ ]` or `[~]` status only, with complete dependencies.
- **On-demand context**: `scripts/build_agent_context_packet.py`, `scripts/dispatch_sdd_task.py`, `tests/architecture/test_agent_playbook_contracts.py`.
- **Kill/defer criteria**: Stop if context packets intentionally remain available for completed or dependency-blocked tasks.
- **Eval/repair signal**: context packet CLI accepting a completed task, accepting a dependency-blocked task, or dispatcher/context-packet guard drift.
- **Implementation**: Move dispatchability checks into the context-packet module and reuse them from the dispatcher.
- **Verification**: `uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_agent_playbook_contracts.py::test_context_packet_cli_refuses_completed_task tests/architecture/test_agent_playbook_contracts.py::test_context_packet_cli_refuses_unmet_dependencies -q`
- **Review owner**: parent
- **Status**: [x]

### Task 11 - Emit subagent mode constraints

- **File(s)**: `scripts/build_agent_context_packet.py`, `scripts/dispatch_sdd_task.py`, `docs/agent-playbook/context-packet-template.md`, `docs/agent-playbook/subagent-handoff-template.md`, `docs/agent-playbook/factory-operating-model.md`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/completed/2026-06-11-executable-harness-followup`
- **Owner**: parent
- **Depends on**: Task 10
- **Touch set**: `scripts/build_agent_context_packet.py`, `scripts/dispatch_sdd_task.py`, `docs/agent-playbook/context-packet-template.md`, `docs/agent-playbook/subagent-handoff-template.md`, `docs/agent-playbook/factory-operating-model.md`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/completed/2026-06-11-executable-harness-followup`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with 2026-06-09-agent-playbook-skill-hard-cut for shared agent playbook docs and generated index updates.
- **Failing test first**: `tests/architecture/test_agent_playbook_contracts.py::test_context_packet_cli_emits_mode_constraints` and `tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_dispatch_cli_emits_mode_constraints` - prove subagent context and handoff outputs expose deterministic mode-specific edit constraints.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Generated subagent context must state read-only and review-only no-edit boundaries, while write-allowed changes must stay inside Owned scope and avoid Do not touch.
- **On-demand context**: `scripts/build_agent_context_packet.py`, `scripts/dispatch_sdd_task.py`, `docs/agent-playbook/subagent-handoff-template.md`, `docs/agent-playbook/context-packet-template.md`.
- **Kill/defer criteria**: Stop if subagent modes are intentionally kept as prompt-only convention instead of generated constraints.
- **Eval/repair signal**: missing `Mode constraints:` in generated context packets or handoffs, mode text drift between generator and template, or task handoff output with implicit edit authority.
- **Implementation**: Add shared mode constraint lines to context-packet generation, reuse them in dry-run handoffs, and update playbook templates/model docs.
- **Verification**: `uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_agent_playbook_contracts.py::test_context_packet_cli_emits_mode_constraints tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_dispatch_cli_emits_mode_constraints -q`
- **Review owner**: parent
- **Status**: [x]

### Task 12 - Validate handoff mode constraints

- **File(s)**: `scripts/agent_mode_constraints.py`, `scripts/build_agent_context_packet.py`, `scripts/dispatch_sdd_task.py`, `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/completed/2026-06-11-executable-harness-followup`
- **Owner**: parent
- **Depends on**: Task 11
- **Touch set**: `scripts/agent_mode_constraints.py`, `scripts/build_agent_context_packet.py`, `scripts/dispatch_sdd_task.py`, `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/completed/2026-06-11-executable-harness-followup`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with 2026-06-09-agent-playbook-skill-hard-cut for shared SDD validator, agent playbook generators, and generated index updates.
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_handoff_mode_constraints` - proves delegated handoff artifacts cannot omit generated mode-specific edit constraints.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: The validator and generators must share one mode-constraint source; handoff artifacts must contain `Mode constraints:` and the exact line matching their `Mode:`.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, `scripts/build_agent_context_packet.py`, `scripts/dispatch_sdd_task.py`, `tests/architecture/test_sdd_artifact_validator.py`.
- **Kill/defer criteria**: Stop if delegated handoff artifact validation intentionally remains weaker than generated handoff output.
- **Eval/repair signal**: delegated handoff artifact accepted without `Mode constraints:`, generator/validator mode text drift, or false valid report noise hiding handoff defects.
- **Implementation**: Extract shared mode constraints, make generators reuse them, and require matching mode constraints in delegated handoff artifact validation.
- **Verification**: `uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_handoff_mode_constraints -q`
- **Review owner**: parent
- **Status**: [x]

### Task 13 - Validate embedded context packet mode constraints

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/completed/2026-06-11-executable-harness-followup`
- **Owner**: parent
- **Depends on**: Task 12
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/completed/2026-06-11-executable-harness-followup`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with 2026-06-09-agent-playbook-skill-hard-cut for shared SDD validator, delegated-handoff fixtures, and generated index updates.
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_embedded_context_packet_mode_constraints` - proves delegated handoffs cannot embed stale Context Packet blocks that omit the matching mode constraints.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: A delegated handoff artifact must embed a Context Packet fenced block with the same feature/task, same mode, and matching mode constraints as the handoff itself.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `scripts/agent_mode_constraints.py`.
- **Kill/defer criteria**: Stop if embedded Context Packet validation intentionally remains weaker than generated context-packet output.
- **Eval/repair signal**: stale embedded context packet accepted, embedded mode drift, missing embedded `Mode constraints:`, or handoff validation depending only on top-level fields.
- **Implementation**: Locate the matching embedded Context Packet fenced block and validate its mode and mode constraints against the handoff.
- **Verification**: `uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_embedded_context_packet_mode_constraints -q`
- **Review owner**: parent
- **Status**: [x]

### Task 14 - Separate top-level handoff validation from embedded context

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/completed/2026-06-11-executable-harness-followup`
- **Owner**: parent
- **Depends on**: Task 13
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/completed/2026-06-11-executable-harness-followup`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with 2026-06-09-agent-playbook-skill-hard-cut for shared SDD validator, delegated-handoff fixtures, and generated index updates.
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_top_level_handoff_mode_constraints` - proves embedded Context Packet constraints cannot satisfy missing top-level handoff constraints.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Top-level handoff title, mode constraints, and report-validation command must be validated outside fenced blocks; embedded Context Packet content is validated separately.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `scripts/agent_mode_constraints.py`.
- **Kill/defer criteria**: Stop if fenced context packet content intentionally remains allowed to satisfy top-level handoff obligations.
- **Eval/repair signal**: top-level handoff missing `Mode constraints:` but passing because embedded context contains them, or report command token checks satisfied from fenced content.
- **Implementation**: Validate top-level handoff obligations against text with fenced blocks removed while keeping embedded Context Packet validation separate.
- **Verification**: `uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_top_level_handoff_mode_constraints -q`
- **Review owner**: parent
- **Status**: [x]

### Task 15 - Require exact report validation command

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/completed/2026-06-11-executable-harness-followup`
- **Owner**: parent
- **Depends on**: Task 14
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/completed/2026-06-11-executable-harness-followup`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with 2026-06-09-agent-playbook-skill-hard-cut for shared SDD validator, delegated-handoff fixtures, and generated index updates.
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_exact_report_validation_command` - proves token inventories cannot satisfy report validation command requirements.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Delegated handoff artifacts must include the exact top-level command `uv run python scripts/validate_subagent_report.py --feature <slug> --task <number> --mode <mode> --report <report.md>`; disconnected tokens do not satisfy the contract.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `scripts/validate_subagent_report.py`.
- **Kill/defer criteria**: Stop if report-validation command enforcement intentionally remains token-only.
- **Eval/repair signal**: delegated handoff accepted with token inventory, wrong command ordering, missing `uv run python`, or command hidden in fenced content.
- **Implementation**: Replace token-presence validation with exact top-level command validation.
- **Verification**: `uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_exact_report_validation_command -q`
- **Review owner**: parent
- **Status**: [x]

### Task 16 - Match exact task numbers across subagent CLIs

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `scripts/build_agent_context_packet.py`, `scripts/dispatch_sdd_task.py`, `scripts/validate_subagent_report.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/completed/2026-06-11-executable-harness-followup`
- **Owner**: parent
- **Depends on**: Task 15
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `scripts/build_agent_context_packet.py`, `scripts/dispatch_sdd_task.py`, `scripts/validate_subagent_report.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/completed/2026-06-11-executable-harness-followup`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with 2026-06-09-agent-playbook-skill-hard-cut for shared agent playbook CLIs, tests, and generated index updates.
- **Failing test first**: `tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_clis_match_exact_task_numbers` - proves `--task 1` cannot bind to `Task 10` when the task board lists Task 10 first.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Context packet, dispatch, and report-validation CLIs must resolve task selectors through exact numeric task ids, not title-prefix matching.
- **On-demand context**: `scripts/build_agent_context_packet.py`, `scripts/dispatch_sdd_task.py`, `scripts/validate_subagent_report.py`, `scripts/validate_sdd_artifacts.py`.
- **Kill/defer criteria**: Stop if any subagent CLI intentionally keeps prefix-based task lookup.
- **Eval/repair signal**: `--task 1` emits Task 10 context, dispatch handoff titles drift, or report validation checks the wrong task fields.
- **Implementation**: Add shared exact task lookup to the SDD validator module and reuse it from all subagent task CLIs.
- **Verification**: `uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_clis_match_exact_task_numbers -q`
- **Review owner**: parent
- **Status**: [x]

### Task 17 - Require task-bound subagent report validation

- **File(s)**: `scripts/validate_subagent_report.py`, `scripts/subagent_report_contract.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/completed/2026-06-11-executable-harness-followup`
- **Owner**: parent
- **Depends on**: Task 16
- **Touch set**: `scripts/validate_subagent_report.py`, `scripts/subagent_report_contract.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/completed/2026-06-11-executable-harness-followup`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with 2026-06-09-agent-playbook-skill-hard-cut for shared subagent report validator, report contract tests, and generated index updates.
- **Failing test first**: `tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_requires_task_binding` - proves unbound reports cannot pass weak generic validation.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `validate_subagent_report.py` must require `--feature` and `--task`; report validation must always run task scope, required-reading, and verification-command checks.
- **On-demand context**: `scripts/validate_subagent_report.py`, `scripts/subagent_report_contract.py`, `tests/architecture/test_agent_playbook_contracts.py`.
- **Kill/defer criteria**: Stop if generic unbound subagent reports intentionally remain accepted.
- **Eval/repair signal**: unbound report validation returns 0, task touch set drift is not checked, or report verification command does not match the selected task.
- **Implementation**: Remove optional task binding from the CLI and make the report contract require task fields.
- **Verification**: `uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_requires_task_binding -q`
- **Review owner**: parent
- **Status**: [x]

### Task 18 - Reject noncanonical task selectors

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `scripts/build_agent_context_packet.py`, `scripts/dispatch_sdd_task.py`, `scripts/validate_subagent_report.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/completed/2026-06-11-executable-harness-followup`
- **Owner**: parent
- **Depends on**: Task 17
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `scripts/build_agent_context_packet.py`, `scripts/dispatch_sdd_task.py`, `scripts/validate_subagent_report.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/completed/2026-06-11-executable-harness-followup`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with 2026-06-09-agent-playbook-skill-hard-cut for shared agent playbook CLIs, selector semantics, tests, and generated index updates.
- **Failing test first**: `tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_clis_reject_noncanonical_numeric_selectors` - proves `--task 01` cannot bind to `Task 1`.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Task selectors must be canonical positive integers with no leading zeroes across context packet, dispatch, and report-validation CLIs.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, `scripts/build_agent_context_packet.py`, `scripts/dispatch_sdd_task.py`, `scripts/validate_subagent_report.py`.
- **Kill/defer criteria**: Stop if `--task 01` remains accepted as an alias for `--task 1`.
- **Eval/repair signal**: noncanonical task selector emits context, handoff, or report validation for a different canonical command.
- **Implementation**: Add shared canonical task selector validation and reuse it from all subagent task CLIs.
- **Verification**: `uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_clis_reject_noncanonical_numeric_selectors -q`
- **Review owner**: parent
- **Status**: [x]

### Task 19 - Reject noncanonical SDD task identifiers

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/completed/2026-06-11-executable-harness-followup`
- **Owner**: parent
- **Depends on**: Task 18
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/completed/2026-06-11-executable-harness-followup`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with 2026-06-09-agent-playbook-skill-hard-cut for shared SDD validator, task identity semantics, tests, and generated index updates.
- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::test_tasks_reject_noncanonical_dependency_references` and `tests/architecture/test_sdd_artifact_validator.py::test_tasks_reject_noncanonical_number_headings` - prove `Task 01` cannot alias `Task 1` in SDD records.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: SDD task headings and dependency references must use canonical positive integers with no leading zeroes.
- **On-demand context**: `scripts/validate_sdd_artifacts.py`, `tests/architecture/test_sdd_artifact_validator.py`.
- **Kill/defer criteria**: Stop if `Task 01` remains accepted as an alias for `Task 1` in any SDD record field.
- **Eval/repair signal**: noncanonical task heading passes validation, dependency aliases a different canonical task, or generated task identity drifts from CLI selector semantics.
- **Implementation**: Tighten task heading and dependency-reference parsing to canonical task numbers only.
- **Verification**: `uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_sdd_artifact_validator.py::test_tasks_reject_noncanonical_dependency_references tests/architecture/test_sdd_artifact_validator.py::test_tasks_reject_noncanonical_number_headings -q`
- **Review owner**: parent
- **Status**: [x]

### Task 20 - Bind subagent report mode outside fenced blocks

- **File(s)**: `scripts/subagent_report_contract.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/completed/2026-06-11-executable-harness-followup`
- **Owner**: parent
- **Depends on**: Task 19
- **Touch set**: `scripts/subagent_report_contract.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/completed/2026-06-11-executable-harness-followup`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with 2026-06-09-agent-playbook-skill-hard-cut for shared subagent report contract semantics, tests, and generated index updates.
- **Failing test first**: `tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_rejects_mode_inside_fenced_block` - proves fenced report examples cannot satisfy the handoff mode binding.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Subagent report `Mode:` must be a top-level line outside fenced blocks and must match the handoff mode passed to the validator.
- **On-demand context**: `scripts/subagent_report_contract.py`, `scripts/validate_subagent_report.py`, `tests/architecture/test_agent_playbook_contracts.py`.
- **Kill/defer criteria**: Stop if fenced report examples remain accepted as mode evidence.
- **Eval/repair signal**: report validation passes when `Mode:` appears only inside a fenced block.
- **Implementation**: Strip fenced blocks before checking the report mode line and require a top-level `Mode: <mode>` match.
- **Verification**: `uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_rejects_mode_inside_fenced_block -q`
- **Review owner**: parent
- **Status**: [x]

### Task 21 - Bind subagent report sections outside fenced blocks

- **File(s)**: `scripts/subagent_report_contract.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/completed/2026-06-11-executable-harness-followup`
- **Owner**: parent
- **Depends on**: Task 20
- **Touch set**: `scripts/subagent_report_contract.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/completed/2026-06-11-executable-harness-followup`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with 2026-06-09-agent-playbook-skill-hard-cut for shared subagent report contract semantics, tests, and generated index updates.
- **Failing test first**: `tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_rejects_sections_inside_fenced_block` - proves fenced report examples cannot satisfy required report sections.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Subagent report `##` headings must be top-level lines outside fenced blocks; fenced examples may not satisfy required sections.
- **On-demand context**: `scripts/subagent_report_contract.py`, `scripts/validate_subagent_report.py`, `tests/architecture/test_agent_playbook_contracts.py`.
- **Kill/defer criteria**: Stop if fenced report examples remain accepted as required section evidence.
- **Eval/repair signal**: report validation passes when required `##` headings appear only inside a fenced block.
- **Implementation**: Ignore fenced-block headings when parsing report sections while preserving fenced command output inside top-level Verification Evidence.
- **Verification**: `uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_rejects_sections_inside_fenced_block -q`
- **Review owner**: parent
- **Status**: [x]

### Task 22 - Bind subagent report claims outside fenced blocks

- **File(s)**: `scripts/subagent_report_contract.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/completed/2026-06-11-executable-harness-followup`
- **Owner**: parent
- **Depends on**: Task 21
- **Touch set**: `scripts/subagent_report_contract.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/completed/2026-06-11-executable-harness-followup`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with 2026-06-09-agent-playbook-skill-hard-cut for shared subagent report contract semantics, tests, and generated index updates.
- **Failing test first**: `tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_rejects_scope_and_reading_claims_inside_fenced_blocks` - proves fenced examples cannot satisfy scope or required-reading claims.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: Scope, changed-files, and required-reading report claims must be evaluated from non-fenced section text; only Verification Evidence may rely on fenced command transcripts.
- **On-demand context**: `scripts/subagent_report_contract.py`, `scripts/validate_subagent_report.py`, `tests/architecture/test_agent_playbook_contracts.py`.
- **Kill/defer criteria**: Stop if fenced report examples remain accepted as task-bound claim evidence.
- **Eval/repair signal**: report validation passes when scope or required-reading claims appear only inside a fenced block.
- **Implementation**: Strip fenced blocks before validating non-verification report claims while preserving fenced command output parsing for Verification Evidence.
- **Verification**: `uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_rejects_scope_and_reading_claims_inside_fenced_blocks -q`
- **Review owner**: parent
- **Status**: [x]

### Task 23 - Reject ambiguous subagent report modes

- **File(s)**: `scripts/subagent_report_contract.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/completed/2026-06-11-executable-harness-followup`
- **Owner**: parent
- **Depends on**: Task 22
- **Touch set**: `scripts/subagent_report_contract.py`, `tests/architecture/test_agent_playbook_contracts.py`, `docs/sdd/features/completed/2026-06-11-executable-harness-followup`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with 2026-06-09-agent-playbook-skill-hard-cut for shared subagent report contract semantics, tests, and generated index updates.
- **Failing test first**: `tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_rejects_multiple_top_level_modes` - proves multiple top-level modes cannot satisfy the report mode binding.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: A subagent report must contain exactly one top-level `Mode:` line and it must match the handoff mode passed to the validator.
- **On-demand context**: `scripts/subagent_report_contract.py`, `scripts/validate_subagent_report.py`, `tests/architecture/test_agent_playbook_contracts.py`.
- **Kill/defer criteria**: Stop if any report with multiple top-level modes remains accepted.
- **Eval/repair signal**: report validation passes when a matching mode appears beside another top-level mode.
- **Implementation**: Parse all top-level report modes outside fenced blocks and accept only the single expected mode.
- **Verification**: `uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_rejects_multiple_top_level_modes -q`
- **Review owner**: parent
- **Status**: [x]
