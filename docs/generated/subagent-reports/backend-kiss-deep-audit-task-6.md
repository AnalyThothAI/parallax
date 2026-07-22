# Worker kernel and concrete settings hard cut

Mode: write-allowed

## Findings

- Replaced the duplicated one-shot and continuous-loop iteration bookkeeping with one `_run_iteration` path and the existing `running` state.
- Moved generic worker fields down to only the concrete settings models that consume them.
- Removed unused `BackoffPolicy.kind`, `write_default_workers_config`, and tests that only guarded retired shapes.

## Scope Adherence

Owned scope: pass

Conflict set: pass

## Changed Files

- `src/parallax/platform/runtime/worker_base.py`
- `src/parallax/platform/config/settings.py`
- `tests/unit/test_worker_base_runtime.py`
- `tests/unit/test_worker_settings.py`

## Required Reading Evidence

Task classification: worker-kernel and configuration implementation.

Read `AGENTS.md`, `docs/agent-playbook/task-reading-matrix.md`, worker docs, the runtime audit report, and the concrete settings consumers named by Task 6.

## Verification Evidence

```text
$ uv run pytest -q tests/unit/test_worker_base_runtime.py tests/unit/test_run_worker_once.py tests/unit/test_worker_settings.py tests/unit/test_settings.py
........................................................................ [ 77%]
.....................                                                    [100%]
93 passed in 1.25s
exit code: 0
```

## Remaining Risks

- Repository-level configuration and worker-factory suites remain required to detect an indirect field consumer.
