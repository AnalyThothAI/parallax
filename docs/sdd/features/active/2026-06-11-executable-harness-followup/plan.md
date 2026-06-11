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
- `tests/architecture/test_harness_structure.py`: assert README/template guidance names the active-record bound.
- `docs/sdd/README.md`, `docs/sdd/_templates/tasks-template.md`: document split-or-supersede guidance for active records.
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

## Verification

Verification evidence lives in `docs/sdd/features/active/2026-06-11-executable-harness-followup/verification.md`.
