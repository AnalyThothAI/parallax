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

## Verification

Verification evidence lives in `docs/sdd/features/active/2026-06-11-executable-harness-followup/verification.md`.
