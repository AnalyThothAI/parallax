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

## Verification commands

Not final completion evidence. Final completion still requires `make check-all` through the completion gate before this record moves to `completed`.

## Coverage

| metric | value | threshold | status |
|--------|-------|-----------|--------|
| architecture and SDD artifact tests | 135 tests | >= targeted harness tests | Pass |
| SDD active gates | 2 active features | all active clarify/checklist/analyze/implement gates pass | Pass |

## Skipped tests

Number of skipped tests in the run above: 0

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
```
