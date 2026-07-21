---
name: parallax-worker-debugging
description: Diagnose Parallax worker backlog, stale read models, delayed catch-up, queue drift, timeout loops, or worker status issues. Use for "Worker Backlog Or Stuck Worker" tasks.
---

# Parallax Worker Debugging

Use this skill for worker runtime incidents. Do not guess from a log line. Trace facts, dirty targets, jobs, bounded catch-up, status payloads, and public read-model symptoms separately.

## Required Reading

1. `AGENTS.md`
2. `docs/agent-playbook/task-reading-matrix.md`
3. `docs/WORKER_FLOW.md`
4. `docs/WORKERS.md`
5. `docs/RELIABILITY.md`
6. `src/parallax/app/runtime/worker_manifest.py`
7. The owning domain `src/parallax/domains/<domain>/ARCHITECTURE.md`

## Workflow

1. Classify the task as `Worker Backlog Or Stuck Worker`.
2. Name the worker manifest key and owning domain.
3. Separate durable facts, dirty targets, job rows, catch-up cadence, status payloads, and public route symptoms.
4. Inspect the current diagnostic surface first: `uv run parallax ops --help`; then choose the relevant `queue-inspect`, `projection-status`, or validation command.
5. Read the smallest domain-specific worker tests before proposing a fix.
6. If behavior changes, write the regression test first and verify it fails.
7. Implement one root-cause fix. Do not add compatibility paths for retired queue, lifecycle, or read-model surfaces.
8. Verify with the smallest relevant worker unit/integration tests plus architecture tests.

## Verification Commands

- `uv run pytest tests/architecture/test_kiss_runtime_invariants.py`
- Targeted worker unit or integration test for the changed domain.

## Output

- Root cause with file paths.
- Evidence by layer: facts, control plane, interval catch-up, read model, public route.
- Changed files, if any.
- Verification command and exit status.
- Remaining risk, especially skipped integration or live-data checks.
