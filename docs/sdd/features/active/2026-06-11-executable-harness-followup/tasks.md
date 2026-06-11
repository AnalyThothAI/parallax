# Tasks - Executable Harness Followup

**Status**: In Progress
**Owning plan**: `docs/sdd/features/active/2026-06-11-executable-harness-followup/plan.md`
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
| Implement | Tasks 1-4 implement the validator, migration, documentation contract, stale-template cleanup, and machine-readable final status tokens. |
| Verify | Verification artifact captures RED/GREEN command output. |

## Tasks

### Task 1 - Bound active SDD task boards

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/active/2026-06-11-executable-harness-followup`, `docs/sdd/features/completed/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: none
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, `tests/architecture/test_sdd_artifact_validator.py`, `docs/sdd/features/active/2026-06-11-executable-harness-followup`, `docs/sdd/features/completed/2026-06-09-executable-harness-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with 2026-06-09-agent-playbook-skill-hard-cut for shared generated SDD index updates.
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

- **File(s)**: `docs/WORKFLOW.md`, `docs/sdd/README.md`, `docs/sdd/_templates/tasks-template.md`, `tests/architecture/test_harness_structure.py`, `docs/sdd/features/active/2026-06-11-executable-harness-followup`
- **Owner**: parent
- **Depends on**: Task 1
- **Touch set**: `docs/WORKFLOW.md`, `docs/sdd/README.md`, `docs/sdd/_templates/tasks-template.md`, `tests/architecture/test_harness_structure.py`, `docs/sdd/features/active/2026-06-11-executable-harness-followup`, `docs/generated/sdd-work-index.md`
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

- **File(s)**: `docs/sdd/_templates/verification-template.md`, `tests/architecture/test_harness_structure.py`, `docs/sdd/features/active/2026-06-11-executable-harness-followup`
- **Owner**: parent
- **Depends on**: Task 2
- **Touch set**: `docs/sdd/_templates/verification-template.md`, `tests/architecture/test_harness_structure.py`, `docs/sdd/features/active/2026-06-11-executable-harness-followup`, `docs/generated/sdd-work-index.md`
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

- **File(s)**: `scripts/validate_sdd_artifacts.py`, `docs/sdd/_templates/verification-template.md`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_harness_structure.py`, `docs/sdd/features/active/2026-06-11-executable-harness-followup`
- **Owner**: parent
- **Depends on**: Task 3
- **Touch set**: `scripts/validate_sdd_artifacts.py`, `docs/sdd/_templates/verification-template.md`, `tests/architecture/test_sdd_artifact_validator.py`, `tests/architecture/test_harness_structure.py`, `docs/sdd/features/active/2026-06-11-executable-harness-followup`, `docs/generated/sdd-work-index.md`
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
