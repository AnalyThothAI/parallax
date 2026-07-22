# Runtime and composition KISS audit

Mode: read-only

## Findings

- CUT: `WorkerBase.running` and `_active_run_loops` encode the same non-overlap state, while `run()` and `run_one_iteration()` duplicate iteration bookkeeping. Keep one `running` guard and one iteration path.
- CUT: `PerWorkerSettings` exposes knobs to workers that never consume them; keep only lifecycle fields in the base model and declare work/lease/timeout knobs on their actual consumers. Remove the unused `BackoffPolicy.kind` discriminator.
- CUT: the News projection repair command has one real domain but exposes `all/news`, a conditional branch, and a nested future-domain payload. Move it to `app/operations` and make News explicit.
- CUT: provider wiring duplicates chain/address normalization already owned by `domains/asset_market/chain_identity.py`; use the existing chain-aware policy at the domain adapter boundary.
- CUT: remove malformed internal `OkxProviderBundle` cleanup branches, the unused pooled `repository_session`, the unused standalone worker-config writer, and single-instance queue descriptor machinery.
- CUT: move operational query/diagnostic modules out of `app/runtime`; reuse `app/operations/queue_health.py` for the single notification queue summary while preserving the exact HTTP payload.
- CUT: remove repeated retired-command, retired-setting, private-field, and source-string tests where current parser, integration, schema, or root architecture tests already prove behavior.
- KEEP: the static worker manifest, factories, scheduler, `InactiveWorker`, and distinct disabled/operator-not-started/unavailable semantics.
- KEEP: `RuntimeSnapshot`, split API/worker pools, zero-business-SQL status, exact API schemas, provider fallback, terminal evidence, and agent execution audit state.
- DEFER: physical PostgreSQL/index cuts, provider fallback removal, and bootstrap API redesign require live or broader evidence.

## Scope Adherence

Owned scope: pass

Conflict set: pass

The audit was read-only and did not touch frontend, migrations, skills, or other active feature scopes.

## Changed Files

None.

## Required Reading Evidence

Task classification: architecture and KISS implementation audit.

Read `AGENTS.md`, `docs/agent-playbook/task-reading-matrix.md`, `docs/ARCHITECTURE.md`, `docs/WORKERS.md`, `docs/WORKER_FLOW.md`, `docs/RELIABILITY.md`, `docs/CONTRACTS.md`, `docs/AGENT_EXECUTION.md`, and the current implementation audit before inspecting source and tests.

## Verification Evidence

```text
$ uv run pytest -q tests/architecture/test_kiss_runtime_invariants.py
............                                                             [100%]
12 passed in 2.32s
exit code: 0
```

## Remaining Risks

- Queue consolidation must adapt to the existing exact API schema rather than expose the CLI health object directly.
- Worker settings cuts must be checked against the operator-owned sparse `workers.yaml` without printing private values.
- Non-EVM address case and unavailable-provider semantics need targeted regression coverage.
