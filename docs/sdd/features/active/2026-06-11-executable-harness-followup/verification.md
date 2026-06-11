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
| AC2 - SDD docs teach the bound. | Pass | `uv --cache-dir /private/tmp/parallax-uv-cache run --no-sync pytest tests/architecture/test_harness_structure.py::test_sdd_docs_describe_bounded_active_feature_records -q` failed RED before README/template guidance named the bound, then passed after docs and template updates. |

## Verification commands

Not final completion evidence. Final completion still requires `make check-all` through the completion gate before this record moves to `completed`.

## Coverage

| metric | value | threshold | status |
|--------|-------|-----------|--------|
| targeted architecture tests | 1 test | >= 1 | Pass |

## Skipped tests

Number of skipped tests in the run above: 0

## E2E golden path

- [x] /readyz returned 200
- [x] writer wrote a row visible to a separate process
- [x] /api/recent returned the injected event
- [x] WS /ws/live pushed within 5s
- [x] testcontainers PG and uvicorn subprocess cleaned up

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
```
