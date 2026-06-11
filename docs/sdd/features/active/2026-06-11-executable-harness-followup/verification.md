# Verification - Executable Harness Followup

**Status**: In Progress
**Date**: 2026-06-11
**Owning spec**: `docs/sdd/features/active/2026-06-11-executable-harness-followup/spec.md`
**Owning plan**: `docs/sdd/features/active/2026-06-11-executable-harness-followup/plan.md`
**Branch**: `main`
**Worktree**: `main`
**Approved by**: qinghuan
**Approved at**: 2026-06-11

## Spec compliance

| Acceptance criterion | Status | Evidence |
|----------------------|--------|----------|
| AC1 - Active records stay bounded. | Pass | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_active_feature_rejects_unbounded_task_board tests/architecture/test_sdd_artifact_validator.py::test_validator_issue_codes_are_registered_for_generated_lifecycle_index -q` failed RED before validator support, then passed after `active-feature-too-large` enforcement, taxonomy registration, and successor migration. |
| AC2 - SDD docs teach the bound. | Pass | `uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_harness_structure.py::test_sdd_docs_describe_bounded_active_feature_records -q` failed RED first for missing README/template guidance, failed RED again when `docs/WORKFLOW.md` was added to the executable contract, then passed after workflow docs and templates named the bound. |
| AC3 - Verification template avoids stale section anchors. | Pass | `uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_harness_structure.py::test_sdd_verification_template_avoids_stale_spec_section_anchors -q` passed after the RED test caught `spec §6.4` and the template was changed to reference the current feature spec. |
| AC4 - Completion status tokens are machine-readable. | Pass | `uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_rejects_symbolic_completion_status_tokens tests/architecture/test_harness_structure.py::test_sdd_verification_template_uses_machine_readable_status_examples -q` failed RED before validator hardening, then passed after checkmark status compatibility was removed and template examples used `Pass`/`Fail`. |
| AC5 - Verification status tokens are lifecycle-wide. | Pass | `uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_sdd_artifact_validator.py::test_verification_tables_reject_symbolic_status_tokens_before_final_verification -q` failed RED before lifecycle-wide verification table status validation, then passed after `verification-status-token-invalid` enforcement and existing SDD status-cell cleanup. |
| AC6 - Active records use current SDD lifecycle commands. | Pass | `uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_sdd_artifact_validator.py::test_active_records_reject_legacy_sdd_lifecycle_check_flags -q` failed RED before active-record lifecycle command validation, then passed after `active-sdd-lifecycle-check-flag-invalid` enforcement and active agent-playbook command cleanup. |
| AC7 - Active records do not fake final transcripts. | Pass | `uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_sdd_artifact_validator.py::test_active_records_reject_placeholder_final_verification_transcripts -q` failed RED before active placeholder-final-evidence validation, then passed after `active-placeholder-final-evidence` enforcement and active agent-playbook transcript cleanup. |
| AC8 - Active skipped-test accounting is final-run-bound. | Pass | `uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_sdd_artifact_validator.py::test_active_records_reject_skipped_count_without_final_evidence -q` failed RED before active skipped-test accounting validation, then passed after `active-skipped-count-without-final-evidence` enforcement and active non-final skip-count cleanup. |
| AC9 - Verification templates fail closed. | Pass | `uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_sdd_artifact_validator.py::test_active_records_reject_template_placeholder_final_verification_transcripts tests/architecture/test_harness_structure.py::test_sdd_verification_template_does_not_embed_fake_final_exit_code -q` failed RED before template placeholder validation and fail-closed template output, then passed after both were enforced. |
| AC10 - Subagent context packets are dispatch-bound. | Pass | `uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_agent_playbook_contracts.py::test_context_packet_cli_refuses_completed_task tests/architecture/test_agent_playbook_contracts.py::test_context_packet_cli_refuses_unmet_dependencies -q` failed RED after fixture cleanup because context packets still accepted non-dispatchable tasks, then passed after context packet and dispatcher shared one dispatchability guard. |
| AC11 - Subagent mode constraints are generated. | Pass | `uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_agent_playbook_contracts.py::test_context_packet_cli_emits_mode_constraints tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_dispatch_cli_emits_mode_constraints -q` passed after shared mode constraint lines were emitted and playbook templates were updated; the same targeted tests failed RED first because context packet and handoff output lacked `Mode constraints:`. |
| AC12 - Handoff mode constraints are validated. | Pass | `uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_handoff_mode_constraints -q` passed after shared mode constraints were extracted and delegated handoff artifact validation required the matching `Mode constraints:` line; the same test failed RED first because the validator accepted a handoff without mode constraints. |
| AC13 - Embedded context packet mode constraints are validated. | Pass | `uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_embedded_context_packet_mode_constraints -q` passed after delegated handoff validation required the embedded Context Packet fenced block to carry the same `Mode:` and matching `Mode constraints:`; the same test failed RED first because the validator accepted a stale embedded packet. |
| AC14 - Top-level handoff constraints are scoped outside fenced blocks. | Pass | `uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_top_level_handoff_mode_constraints -q` passed after top-level handoff validation ignored fenced blocks; the same test failed RED first because embedded Context Packet constraints satisfied a missing top-level handoff constraint. |
| AC15 - Handoff report validation command is exact. | Pass | `uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_exact_report_validation_command -q` passed after report-validation command validation changed from token presence to exact runnable top-level command; the same test failed RED first because a token inventory satisfied the old validator. |
| AC16 - Subagent task selectors are exact. | Pass | `uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_clis_match_exact_task_numbers -q` passed after context packet, dispatch, and report-validation CLIs shared exact numeric task lookup; the same test failed RED first because `--task 1` matched a preceding `Task 10`. |

## Verification commands

Not final completion evidence. Final completion still requires `make check-all` through the completion gate before this record moves to `completed`.

## Coverage

| metric | value | threshold | status |
|--------|-------|-----------|--------|
| agent loop and SDD artifact tests | 239 tests | >= targeted harness tests | Pass |
| SDD active gates | 2 active features | all active clarify/checklist/analyze/implement gates pass | Pass |

## Skipped tests

Not final completion evidence. Skipped-test accounting will be recorded with
the final `make check-all` run.

## E2E golden path

Not run for this non-final harness hardening pass; this record remains `In Progress`
and is not claiming final completion evidence.

- [ ] /readyz returned 200
- [ ] writer wrote a row visible to a separate process
- [ ] /api/recent returned the injected event
- [ ] WS /ws/live pushed within 5s
- [ ] testcontainers PG and uvicorn subprocess cleaned up

## Other commands run

```text
$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_active_feature_rejects_unbounded_task_board -q
F                                                                        [100%]
AssertionError: assert 'active-feature-too-large' in set()
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_active_feature_rejects_unbounded_task_board -q
   Building parallax @ file:///Users/qinghuan/Documents/code/parallax
      Built parallax @ file:///Users/qinghuan/Documents/code/parallax
Uninstalled 1 package in 0.92ms
Installed 1 package in 1ms
.                                                                        [100%]
1 passed in 0.02s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_active_feature_rejects_unbounded_task_board tests/architecture/test_sdd_artifact_validator.py::test_validator_issue_codes_are_registered_for_generated_lifecycle_index -q
..                                                                       [100%]
2 passed in 0.06s
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run pytest tests/architecture/test_harness_structure.py::test_sdd_docs_describe_bounded_active_feature_records -q
F                                                                        [100%]
AssertionError: assert '40 structured tasks' in ...
exit code: 1

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run pytest tests/architecture/test_harness_structure.py::test_sdd_docs_describe_bounded_active_feature_records -q
.                                                                        [100%]
1 passed in 0.01s
exit code: 0

$ uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_harness_structure.py::test_sdd_docs_describe_bounded_active_feature_records -q
.                                                                        [100%]
1 passed in 0.01s
exit code: 0

$ uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_harness_structure.py::test_sdd_docs_describe_bounded_active_feature_records -q
F                                                                        [100%]
AssertionError: docs/WORKFLOW.md does not mention '40 structured tasks'
exit code: 1

$ uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_harness_structure.py::test_sdd_docs_describe_bounded_active_feature_records -q
.                                                                        [100%]
1 passed in 0.01s
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py
SDD artifact validation passed.
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py && UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check
wrote docs/generated/sdd-work-index.md
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run python scripts/check_sdd_gate.py --all-active
all active SDD gates passed (clarify/checklist/analyze/implement): 2026-06-09-agent-playbook-skill-hard-cut, 2026-06-11-executable-harness-followup
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run pytest tests/architecture/test_harness_structure.py tests/architecture/test_sdd_artifact_validator.py -q
135 passed in 0.45s
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run ruff check tests/architecture/test_harness_structure.py
All checks passed!
exit code: 0

$ git diff --check
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run pytest tests/architecture/test_harness_structure.py::test_sdd_verification_template_avoids_stale_spec_section_anchors -q
F                                                                        [100%]
AssertionError: assert '§6.4' not in ...
exit code: 1

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run pytest tests/architecture/test_harness_structure.py::test_sdd_verification_template_avoids_stale_spec_section_anchors -q
.                                                                        [100%]
1 passed in 0.01s
exit code: 0

$ uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_harness_structure.py::test_sdd_verification_template_avoids_stale_spec_section_anchors -q
.                                                                        [100%]
1 passed in 0.01s
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run pytest tests/architecture/test_harness_structure.py tests/architecture/test_sdd_artifact_validator.py -q
136 passed in 0.56s
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run python scripts/check_sdd_gate.py --all-active
all active SDD gates passed (clarify/checklist/analyze/implement): 2026-06-09-agent-playbook-skill-hard-cut, 2026-06-11-executable-harness-followup
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run ruff check tests/architecture/test_harness_structure.py
All checks passed!
exit code: 0

$ git diff --check
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run pytest tests/architecture/test_harness_structure.py::test_sdd_verification_template_uses_machine_readable_status_examples -q
F                                                                        [100%]
AssertionError: assert '✅' not in ...
exit code: 1

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run pytest tests/architecture/test_harness_structure.py::test_sdd_verification_template_uses_machine_readable_status_examples -q
.                                                                        [100%]
1 passed in 0.01s
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_rejects_symbolic_completion_status_tokens -q
F                                                                        [100%]
AssertionError: assert 'verified-incomplete-spec-compliance' in set()
exit code: 1

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_rejects_symbolic_completion_status_tokens -q
.                                                                        [100%]
1 passed in 0.03s
exit code: 0

$ uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_rejects_symbolic_completion_status_tokens tests/architecture/test_harness_structure.py::test_sdd_verification_template_uses_machine_readable_status_examples -q
..                                                                       [100%]
2 passed in 0.02s
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run pytest tests/architecture/test_harness_structure.py tests/architecture/test_sdd_artifact_validator.py -q
138 passed in 0.39s
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run python scripts/check_sdd_gate.py --all-active
all active SDD gates passed (clarify/checklist/analyze/implement): 2026-06-09-agent-playbook-skill-hard-cut, 2026-06-11-executable-harness-followup
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run ruff check scripts/validate_sdd_artifacts.py tests/architecture/test_sdd_artifact_validator.py tests/architecture/test_harness_structure.py
E501 Line too long (125 > 120)
exit code: 1

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run ruff check scripts/validate_sdd_artifacts.py tests/architecture/test_sdd_artifact_validator.py tests/architecture/test_harness_structure.py
All checks passed!
exit code: 0

$ git diff --check
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py && UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py && UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check
SDD artifact validation passed.
wrote docs/generated/sdd-work-index.md
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run python scripts/check_sdd_gate.py --all-active
all active SDD gates passed (clarify/checklist/analyze/implement): 2026-06-09-agent-playbook-skill-hard-cut, 2026-06-11-executable-harness-followup
exit code: 0

$ git diff --check
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verification_tables_reject_symbolic_status_tokens_before_final_verification -q
F                                                                        [100%]
AssertionError: assert 'verification-status-token-invalid' in set()
exit code: 1

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verification_tables_reject_symbolic_status_tokens_before_final_verification -q
.                                                                        [100%]
1 passed in 0.03s
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py
error: verification-status-token-invalid: docs/sdd/features/active/2026-06-09-agent-playbook-skill-hard-cut/verification.md: verification table status cells must use machine-readable status words
exit code: 1

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py
SDD artifact validation passed.
exit code: 0

$ uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_sdd_artifact_validator.py::test_verification_tables_reject_symbolic_status_tokens_before_final_verification -q
.                                                                        [100%]
1 passed in 0.03s
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py && UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py && UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check
SDD artifact validation passed.
wrote docs/generated/sdd-work-index.md
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run pytest tests/architecture/test_harness_structure.py tests/architecture/test_sdd_artifact_validator.py -q
139 passed in 0.46s
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run python scripts/check_sdd_gate.py --all-active
all active SDD gates passed (clarify/checklist/analyze/implement): 2026-06-09-agent-playbook-skill-hard-cut, 2026-06-11-executable-harness-followup
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run ruff check scripts/validate_sdd_artifacts.py scripts/regen_sdd_work_index.py tests/architecture/test_sdd_artifact_validator.py tests/architecture/test_harness_structure.py
All checks passed!
exit code: 0

$ git diff --check
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_active_records_reject_legacy_sdd_lifecycle_check_flags -q
F                                                                        [100%]
AssertionError: assert 'active-sdd-lifecycle-check-flag-invalid' in ...
exit code: 1

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_active_records_reject_legacy_sdd_lifecycle_check_flags -q
.                                                                        [100%]
1 passed in 0.03s
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py
error: active-sdd-lifecycle-check-flag-invalid: docs/sdd/features/active/2026-06-09-agent-playbook-skill-hard-cut/tasks.md: active SDD records must not advertise legacy SDD lifecycle --check flags
exit code: 1

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py
SDD artifact validation passed.
exit code: 0

$ uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_sdd_artifact_validator.py::test_active_records_reject_legacy_sdd_lifecycle_check_flags -q
.                                                                        [100%]
1 passed in 0.03s
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py && UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py && UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check
SDD artifact validation passed.
wrote docs/generated/sdd-work-index.md
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run pytest tests/architecture/test_harness_structure.py tests/architecture/test_sdd_artifact_validator.py -q
140 passed in 0.55s
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run python scripts/check_sdd_gate.py --all-active
all active SDD gates passed (clarify/checklist/analyze/implement): 2026-06-09-agent-playbook-skill-hard-cut, 2026-06-11-executable-harness-followup
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run ruff check scripts/validate_sdd_artifacts.py scripts/regen_sdd_work_index.py tests/architecture/test_sdd_artifact_validator.py tests/architecture/test_harness_structure.py
All checks passed!
exit code: 0

$ git diff --check
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_active_records_reject_placeholder_final_verification_transcripts -q
F                                                                        [100%]
AssertionError: assert 'active-placeholder-final-evidence' in set()
exit code: 1

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_active_records_reject_placeholder_final_verification_transcripts -q
.                                                                        [100%]
1 passed in 0.06s
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py
error: active-placeholder-final-evidence: docs/sdd/features/active/2026-06-09-agent-playbook-skill-hard-cut/verification.md: active verification commands must not contain placeholder final transcript evidence
exit code: 1

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py
SDD artifact validation passed.
exit code: 0

$ uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_sdd_artifact_validator.py::test_active_records_reject_placeholder_final_verification_transcripts -q
.                                                                        [100%]
1 passed in 0.02s
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py && UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py && UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check
SDD artifact validation passed.
wrote docs/generated/sdd-work-index.md
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run pytest tests/architecture/test_harness_structure.py tests/architecture/test_sdd_artifact_validator.py -q
141 passed in 0.50s
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run python scripts/check_sdd_gate.py --all-active
all active SDD gates passed (clarify/checklist/analyze/implement): 2026-06-09-agent-playbook-skill-hard-cut, 2026-06-11-executable-harness-followup
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run ruff check scripts/validate_sdd_artifacts.py scripts/regen_sdd_work_index.py tests/architecture/test_sdd_artifact_validator.py tests/architecture/test_harness_structure.py
All checks passed!
exit code: 0

$ git diff --check
exit code: 0

$ uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_sdd_artifact_validator.py::test_active_records_reject_skipped_count_without_final_evidence -q
F                                                                        [100%]
AssertionError: assert 'active-skipped-count-without-final-evidence' in set()
exit code: 1

$ uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_sdd_artifact_validator.py::test_active_records_reject_skipped_count_without_final_evidence -q
.                                                                        [100%]
1 passed in 0.03s
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py
error: active-skipped-count-without-final-evidence: docs/sdd/features/active/2026-06-09-agent-playbook-skill-hard-cut/verification.md: active Skipped tests numeric run-above count requires successful final `make check-all` evidence in Verification commands; use non-final prose until that run exists
error: active-skipped-count-without-final-evidence: docs/sdd/features/active/2026-06-11-executable-harness-followup/verification.md: active Skipped tests numeric run-above count requires successful final `make check-all` evidence in Verification commands; use non-final prose until that run exists
exit code: 1

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py
SDD artifact validation passed.
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py
wrote docs/generated/sdd-work-index.md
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run pytest tests/architecture/test_harness_structure.py tests/architecture/test_sdd_artifact_validator.py -q
142 passed in 0.44s
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run python scripts/check_sdd_gate.py --all-active
all active SDD gates passed (clarify/checklist/analyze/implement): 2026-06-09-agent-playbook-skill-hard-cut, 2026-06-11-executable-harness-followup
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run ruff check scripts/validate_sdd_artifacts.py scripts/regen_sdd_work_index.py tests/architecture/test_sdd_artifact_validator.py tests/architecture/test_harness_structure.py
All checks passed!
exit code: 0

$ git diff --check
exit code: 0

$ uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_sdd_artifact_validator.py::test_active_records_reject_template_placeholder_final_verification_transcripts tests/architecture/test_harness_structure.py::test_sdd_verification_template_does_not_embed_fake_final_exit_code -q
FF                                                                       [100%]
AssertionError: assert 'active-placeholder-final-evidence' in set()
AssertionError: assert '<paste full stdout/stderr here after the final successful run>' in ...
exit code: 1

$ uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_sdd_artifact_validator.py::test_active_records_reject_template_placeholder_final_verification_transcripts tests/architecture/test_harness_structure.py::test_sdd_verification_template_does_not_embed_fake_final_exit_code -q
..                                                                       [100%]
2 passed in 0.04s
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py
SDD artifact validation passed.
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run python scripts/check_sdd_gate.py --all-active
all active SDD gates passed (clarify/checklist/analyze/implement): 2026-06-09-agent-playbook-skill-hard-cut, 2026-06-11-executable-harness-followup
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py
wrote docs/generated/sdd-work-index.md
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run pytest tests/architecture/test_harness_structure.py tests/architecture/test_sdd_artifact_validator.py -q
144 passed in 0.49s
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run ruff check scripts/validate_sdd_artifacts.py tests/architecture/test_sdd_artifact_validator.py tests/architecture/test_harness_structure.py
All checks passed!
exit code: 0

$ git diff --check
exit code: 0

$ uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_agent_playbook_contracts.py::test_context_packet_cli_refuses_completed_task tests/architecture/test_agent_playbook_contracts.py::test_context_packet_cli_refuses_unmet_dependencies -q
FF                                                                       [100%]
AssertionError: assert 'already complete' in ...
AssertionError: assert 'dependencies are not complete' in ...
exit code: 1

$ uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_agent_playbook_contracts.py::test_context_packet_cli_refuses_completed_task tests/architecture/test_agent_playbook_contracts.py::test_context_packet_cli_refuses_unmet_dependencies -q
FF                                                                       [100%]
AssertionError: assert 0 == 1
AssertionError: assert 0 == 1
exit code: 1

$ uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_agent_playbook_contracts.py::test_context_packet_cli_refuses_completed_task tests/architecture/test_agent_playbook_contracts.py::test_context_packet_cli_refuses_unmet_dependencies tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_dispatch_cli_refuses_completed_task tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_dispatch_cli_refuses_unmet_dependencies tests/architecture/test_agent_playbook_contracts.py::test_context_packet_cli tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_dispatch_cli_emits_handoff_for_in_progress_task -q
......                                                                   [100%]
6 passed in 0.19s
exit code: 0

$ uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_agent_playbook_contracts.py::test_context_packet_cli_refuses_completed_task tests/architecture/test_agent_playbook_contracts.py::test_context_packet_cli_refuses_unmet_dependencies -q
..                                                                       [100%]
2 passed in 0.16s
exit code: 0

$ uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_positive_skipped_count_with_freeform_table tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_verify_rejects_positive_skipped_count_with_placeholder_reason tests/architecture/test_agent_playbook_contracts.py::test_sdd_gate_check_cli_accepts_verify_gate_with_final_evidence -q
...                                                                      [100%]
3 passed in 0.17s
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run pytest tests/architecture/test_agent_playbook_contracts.py tests/architecture/test_harness_structure.py tests/architecture/test_sdd_artifact_validator.py -q
232 passed in 11.66s
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run ruff check scripts/build_agent_context_packet.py scripts/dispatch_sdd_task.py tests/architecture/test_agent_playbook_contracts.py tests/architecture/test_harness_structure.py tests/architecture/test_sdd_artifact_validator.py
All checks passed!
exit code: 0

$ git diff --check
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_context_packet_cli_emits_mode_constraints tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_dispatch_cli_emits_mode_constraints -q
FF                                                                       [100%]
AssertionError: assert 'Mode constraints:' in ...
exit code: 1

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_context_packet_cli_emits_mode_constraints tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_dispatch_cli_emits_mode_constraints -q
..                                                                       [100%]
2 passed in 0.13s
exit code: 0

$ uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_agent_playbook_contracts.py::test_context_packet_cli_emits_mode_constraints tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_dispatch_cli_emits_mode_constraints -q
..                                                                       [100%]
2 passed in 0.16s
exit code: 0

$ uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_agent_playbook_contracts.py::test_context_packet_cli_emits_mode_constraints tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_dispatch_cli_emits_mode_constraints -q
..                                                                       [100%]
2 passed in 0.34s
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run ruff check scripts/build_agent_context_packet.py scripts/dispatch_sdd_task.py tests/architecture/test_agent_playbook_contracts.py tests/architecture/test_harness_structure.py tests/architecture/test_sdd_artifact_validator.py
All checks passed!
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run pytest tests/architecture/test_agent_playbook_contracts.py tests/architecture/test_harness_structure.py tests/architecture/test_sdd_artifact_validator.py -q
........................................................................ [ 30%]
........................................................................ [ 61%]
........................................................................ [ 92%]
..................                                                       [100%]
234 passed in 11.97s
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_handoff_mode_constraints -q
F                                                                        [100%]
AssertionError: assert []
exit code: 1

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_handoff_mode_constraints -q
.                                                                        [100%]
1 passed in 0.13s
exit code: 0

$ uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_handoff_mode_constraints -q
.                                                                        [100%]
1 passed in 0.02s
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run pytest tests/architecture/test_agent_playbook_contracts.py tests/architecture/test_harness_structure.py tests/architecture/test_sdd_artifact_validator.py -q
........................................................................ [ 30%]
........................................................................ [ 61%]
........................................................................ [ 91%]
...................                                                      [100%]
235 passed in 12.82s
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run ruff check scripts/agent_mode_constraints.py scripts/build_agent_context_packet.py scripts/dispatch_sdd_task.py scripts/validate_sdd_artifacts.py tests/architecture/test_sdd_artifact_validator.py tests/architecture/test_agent_playbook_contracts.py tests/architecture/test_harness_structure.py
All checks passed!
exit code: 0

$ git diff --check
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_embedded_context_packet_mode_constraints -q
F                                                                        [100%]
AssertionError: assert []
exit code: 1

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_embedded_context_packet_mode_constraints -q
.                                                                        [100%]
1 passed in 0.06s
exit code: 0

$ uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_embedded_context_packet_mode_constraints -q
.                                                                        [100%]
1 passed in 0.02s
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run pytest tests/architecture/test_agent_playbook_contracts.py tests/architecture/test_harness_structure.py tests/architecture/test_sdd_artifact_validator.py -q
........................................................................ [ 30%]
........................................................................ [ 61%]
........................................................................ [ 91%]
....................                                                     [100%]
236 passed in 11.82s
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run ruff check scripts/agent_mode_constraints.py scripts/build_agent_context_packet.py scripts/dispatch_sdd_task.py scripts/validate_sdd_artifacts.py tests/architecture/test_sdd_artifact_validator.py tests/architecture/test_agent_playbook_contracts.py tests/architecture/test_harness_structure.py
All checks passed!
exit code: 0

$ git diff --check
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_top_level_handoff_mode_constraints -q
F                                                                        [100%]
AssertionError: assert []
exit code: 1

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_top_level_handoff_mode_constraints -q
.                                                                        [100%]
1 passed in 0.03s
exit code: 0

$ uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_top_level_handoff_mode_constraints -q
.                                                                        [100%]
1 passed in 0.03s
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run pytest tests/architecture/test_agent_playbook_contracts.py tests/architecture/test_harness_structure.py tests/architecture/test_sdd_artifact_validator.py -q
........................................................................ [ 30%]
........................................................................ [ 60%]
........................................................................ [ 91%]
.....................                                                    [100%]
237 passed in 11.95s
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run ruff check scripts/agent_mode_constraints.py scripts/build_agent_context_packet.py scripts/dispatch_sdd_task.py scripts/validate_sdd_artifacts.py tests/architecture/test_sdd_artifact_validator.py tests/architecture/test_agent_playbook_contracts.py tests/architecture/test_harness_structure.py
All checks passed!
exit code: 0

$ git diff --check
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_exact_report_validation_command -q
F                                                                        [100%]
AssertionError: assert []
exit code: 1

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_exact_report_validation_command -q
.                                                                        [100%]
1 passed in 0.03s
exit code: 0

$ uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_exact_report_validation_command -q
.                                                                        [100%]
1 passed in 0.02s
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py
wrote docs/generated/sdd-work-index.md
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py
SDD artifact validation passed.
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run python scripts/check_sdd_gate.py --all-active
all active SDD gates passed (clarify/checklist/analyze/implement): 2026-06-09-agent-playbook-skill-hard-cut, 2026-06-11-executable-harness-followup
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run pytest tests/architecture/test_agent_playbook_contracts.py tests/architecture/test_harness_structure.py tests/architecture/test_sdd_artifact_validator.py -q
........................................................................ [ 30%]
........................................................................ [ 60%]
........................................................................ [ 90%]
......................                                                   [100%]
238 passed in 12.92s
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run ruff check scripts/agent_mode_constraints.py scripts/build_agent_context_packet.py scripts/dispatch_sdd_task.py scripts/validate_sdd_artifacts.py tests/architecture/test_sdd_artifact_validator.py tests/architecture/test_agent_playbook_contracts.py tests/architecture/test_harness_structure.py
All checks passed!
exit code: 0

$ git diff --check
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_clis_match_exact_task_numbers -q
F                                                                        [100%]
AssertionError: assert '# Context Packet -...t-fixture / Task 10' not in ...
exit code: 1

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_clis_match_exact_task_numbers -q
.                                                                        [100%]
1 passed in 0.12s
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_context_packet_cli tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_dispatch_cli_emits_handoff_for_in_progress_task tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_clis_reject_title_substring_selectors tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_clis_match_exact_task_numbers -q
....                                                                     [100%]
4 passed in 0.29s
exit code: 0

$ uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_clis_match_exact_task_numbers -q
.                                                                        [100%]
1 passed in 0.12s
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py
wrote docs/generated/sdd-work-index.md
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run python scripts/validate_sdd_artifacts.py
SDD artifact validation passed.
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run python scripts/check_sdd_gate.py --all-active
all active SDD gates passed (clarify/checklist/analyze/implement): 2026-06-09-agent-playbook-skill-hard-cut, 2026-06-11-executable-harness-followup
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run pytest tests/architecture/test_agent_playbook_contracts.py tests/architecture/test_harness_structure.py tests/architecture/test_sdd_artifact_validator.py -q
........................................................................ [ 30%]
........................................................................ [ 60%]
........................................................................ [ 90%]
.......................                                                  [100%]
239 passed in 12.80s
exit code: 0

$ UV_NO_SYNC=1 UV_CACHE_DIR=/private/tmp/parallax-uv-cache uv run ruff check scripts/validate_sdd_artifacts.py scripts/build_agent_context_packet.py scripts/dispatch_sdd_task.py scripts/validate_subagent_report.py tests/architecture/test_agent_playbook_contracts.py
All checks passed!
exit code: 0

$ git diff --check
exit code: 0
```
