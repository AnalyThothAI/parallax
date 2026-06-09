# Verification — Executable Harness Hard Cut

**Status**: In Progress
**Date**: 2026-06-09
**Owning spec**: `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut/spec.md`
**Owning plan**: `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut/plan.md`
**Branch**: `codex/agent-factory-eval-harness`
**Worktree**: `.worktrees/agent-factory-eval-harness`
**Approved by**: qinghuan
**Approved at**: 2026-06-09
**Diff**: Pending final diff.

The plan and spec are the contract. This file is the evidence the contract was met. No `done`, `fixed`, or `passing`
claim is allowed without the corresponding output captured below.

## Spec compliance

| Acceptance criterion | Status | Evidence |
|----------------------|--------|----------|
| AC1 — false `Verified` records fail. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py -q` passed. |
| AC2 — incomplete task coordination fails. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py -q` passed. |
| AC3 — coordination board is generated and current. | ✅ | `uv run python scripts/regen_sdd_work_index.py --check` passed. |
| AC4 — SQL helper supports semantic query contracts. | ✅ | `uv run pytest tests/unit/test_query_contract.py tests/unit/domains/macro_intel -q` passed. |
| AC5 — `make check-all` includes deterministic harness gates. | ⚠️ | `make check-all` started and ran the new SDD validator/index gates, then was stopped during integration per user instruction. |
| AC6 — development-agent factory/eval loop is executable. | ✅ | `uv run pytest tests/architecture/test_agent_playbook_contracts.py tests/architecture/test_sdd_artifact_validator.py -q` passed. |
| AC7 — SDD task context-packet CLI is executable. | ✅ | `uv run pytest tests/architecture/test_agent_playbook_contracts.py tests/architecture/test_sdd_artifact_validator.py -q` and `uv run python scripts/build_agent_context_packet.py --feature 2026-06-09-executable-harness-hard-cut --task 7 --mode read-only` passed. |

Deviations from spec:

- None.

Deviations from plan:

- `make check-all` was not completed. User requested on 2026-06-09: "不跑集成测试了 先合并到main吧".

## Verification commands

The only command whose output may be pasted as completion evidence is `make check-all`. Paste the full output below,
including the exit code line, before moving this feature to `completed`.

```text
$ make check-all
SDD artifact validation passed.
make check passed, including frontend typecheck/lint/architecture/format,
Python unit/architecture/contract tests, and compileall.
Stopped during tests/integration per user instruction before integration/e2e/golden/coverage completed.
exit code: 2
```

## Coverage

| metric | value | threshold | status |
|--------|-------|-----------|--------|
| line   | Not run | >= 80% | ❌ |
| branch | Not run | >= 70% | ❌ |

## Skipped tests

Number of skipped tests in the completed `make check` segment: 3

| count | reason | acceptable? |
|-------|--------|-------------|
| 1 | PostgreSQL test database unavailable in non-integration check segment. | Yes for `make check`; not final `check-all` evidence. |
| 1 | Empty architecture parameter set for worker runtime table allowlist. | Yes; existing architecture skip. |
| 1 | Opt-in provider drift check requires `GMGN_PROVIDER_DRIFT=1`. | Yes; live drift diagnostic is opt-in. |

## E2E golden path

Confirm each runtime signal from the spec was asserted:

- [ ] /readyz returned 200
- [ ] writer wrote a row visible to a separate process
- [ ] /api/recent returned the injected event
- [ ] WS /ws/live pushed within 5s
- [ ] testcontainers PG and uvicorn subprocess cleaned up

Not run because integration/e2e/golden gates were intentionally skipped before merging to `main`.

## Other commands run

```text
$ uv run python scripts/validate_sdd_artifacts.py --check
SDD artifact validation passed.

$ uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py tests/unit/test_query_contract.py tests/unit/domains/macro_intel/test_macro_migration_contract.py::test_repository_concept_history_counts_reads_projected_rows tests/architecture/test_agent_playbook_contracts.py::test_sdd_work_index_is_generated_and_current tests/architecture/test_test_lane_contracts.py::test_architecture_tests_declare_harness_taxonomy tests/architecture/test_harness_structure.py::test_make_check_all_runs_executable_sdd_harness -q
10 passed in 0.18s

$ uv run pytest tests/architecture -m architecture -q
365 passed, 1 skipped in 13.00s

$ uv run pytest tests/unit/domains/macro_intel tests/unit/test_query_contract.py -q
154 passed in 0.92s

$ make check
2630 passed, 3 skipped in 24.03s
exit code: 0

$ uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_development_agent_factory_model_is_explicit_and_bounded tests/architecture/test_agent_playbook_contracts.py::test_development_agent_eval_repair_loop_is_defined tests/architecture/test_agent_playbook_contracts.py::test_tasks_template_has_parallel_subagent_contract_fields tests/architecture/test_agent_playbook_contracts.py::test_sdd_work_index_is_generated_and_current tests/architecture/test_sdd_artifact_validator.py::test_tasks_require_filled_coordination_fields -q
5 passed in 0.09s
exit code: 0

$ uv run pytest tests/architecture/test_agent_playbook_contracts.py tests/architecture/test_sdd_artifact_validator.py -q
12 passed in 0.15s
exit code: 0

$ uv run ruff check scripts/validate_sdd_artifacts.py scripts/regen_sdd_work_index.py tests/architecture/test_agent_playbook_contracts.py tests/architecture/test_sdd_artifact_validator.py
All checks passed!
exit code: 0

$ uv run pytest tests/architecture -m architecture -q
367 passed, 1 skipped in 32.73s
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py --check
SDD artifact validation passed.
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ uv run pytest tests/architecture/test_agent_playbook_contracts.py tests/architecture/test_sdd_artifact_validator.py -q
16 passed in 0.11s
exit code: 0

$ uv run python scripts/build_agent_context_packet.py --feature 2026-06-09-executable-harness-hard-cut --task 7 --mode read-only
# Context Packet - 2026-06-09-executable-harness-hard-cut / Task 7
...
exit code: 0
```

## Diff summary

Files changed:

- SDD executable harness: `scripts/validate_sdd_artifacts.py`, `scripts/regen_sdd_work_index.py`, SDD templates, `docs/generated/sdd-work-index.md`.
- Development-agent factory/eval loop: `docs/agent-playbook/factory-operating-model.md`, `docs/agent-playbook/eval-repair-loop.md`, `docs/agent-playbook/task-reading-matrix.md`.
- Test taxonomy and gate wiring: `docs/TESTING.md`, `docs/WORKFLOW.md`, `Makefile`, architecture tests.
- SQL query-contract helper and macro request-path hard cut: `tests/support/query_contract.py`, macro repository/tests.
- Mechanical frontend Prettier drift cleanup: macro pages, macro component test, `web/vite.config.ts`.

Migrations applied:

- None.

Schema or contract changes that consumers must be aware of:

- None.

## Risks observed

- Integration, e2e, golden, and coverage gates were not completed before merging to `main` by explicit user instruction.

## Follow-ups

- Re-run `make check-all` when ready and move this feature record to `completed/` only after exit code 0 evidence exists.
