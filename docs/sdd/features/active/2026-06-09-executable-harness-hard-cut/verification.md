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
| AC8 — SDD dry-run dispatcher emits handoff and refuses completed tasks. | ✅ | `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_dispatch_cli_emits_handoff_for_in_progress_task tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_dispatch_cli_refuses_completed_task -q` passed; real Task 5 dispatch emitted a handoff and real Task 8 dispatch was refused. |
| AC9 — task field values are semantically validated. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_tasks_reject_invalid_coordination_field_values tests/architecture/test_sdd_artifact_validator.py::test_tasks_allow_explicit_none_dependency_and_not_delegated_handoff -q` passed. |
| AC10 — Verified evidence parser ignores stale success snippets. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_ignores_old_success_outside_verification_commands tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_skipped_table_to_match_skip_count -q` passed. |
| AC11 — generated SDD index exposes task-level dispatch state. | ✅ | `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_work_index_renders_task_dispatch_board -q` passed. |
| AC12 — dependency-aware task dispatch is executable. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_tasks_reject_unresolved_dependencies tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_dispatch_cli_refuses_unmet_dependencies tests/architecture/test_agent_playbook_contracts.py::test_sdd_work_index_renders_task_dispatch_board -q` passed. |
| AC13 — subagent return report validation is executable. | ✅ | `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_accepts_evidence_report tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_rejects_unverifiable_or_out_of_scope_report tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_accepts_task_bound_report tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_rejects_task_bound_scope_and_command_drift tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_dispatch_cli_emits_handoff_for_in_progress_task -q` passed. |
| AC14 — parent review outcome is task state. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_review_evidence_fields tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_reject_invalid_review_evidence_values tests/architecture/test_agent_playbook_contracts.py::test_tasks_template_has_parallel_subagent_contract_fields tests/architecture/test_agent_playbook_contracts.py::test_sdd_work_index_renders_task_dispatch_board -q` passed. |
| AC15 — delegated report artifacts are validated. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_report_artifact tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_validate_report_artifact_against_task tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_accepts_task_bound_report -q` passed. |
| AC16 — completed task verification evidence is executable. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_complete_tasks_require_matching_verification_evidence tests/architecture/test_agent_playbook_contracts.py::test_context_packet_cli -q` passed. |
| AC17 — machine-readable `not delegated` token is exact. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_non_delegated_handoff_rejects_prose_suffix tests/architecture/test_sdd_artifact_validator.py::test_tasks_allow_explicit_none_dependency_and_not_delegated_handoff tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_report_artifact -q` passed. |
| AC18 — delegated handoff artifacts are validated. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_handoff_artifact tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_report_artifact -q` passed. |
| AC19 — artifact lifecycle statuses are consistent. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_feature_rejects_mixed_artifact_statuses -q` passed after first failing RED run. |
| AC20 — superseded successor metadata is machine-readable. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_superseded_feature_requires_machine_readable_successor -q` passed after first failing RED run. |
| AC21 — feature directories contain exactly four artifacts. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_feature_rejects_unexpected_artifact_files -q` passed after first failing RED run; legacy macro SDD attachments were deleted. |
| AC22 — completed tasks cannot depend on incomplete tasks. | ✅ | `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_completed_tasks_reject_incomplete_dependencies -q` passed after first failing RED run; Task 6 dependency was corrected from `Tasks 1-5` to `Tasks 1-4`. |

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

$ uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_dispatch_cli_emits_handoff_for_in_progress_task tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_dispatch_cli_refuses_completed_task -q
2 passed in 0.07s
exit code: 0

$ uv run python scripts/dispatch_sdd_task.py --feature 2026-06-09-executable-harness-hard-cut --task 5 --mode read-only
# Subagent Handoff - 2026-06-09-executable-harness-hard-cut / Task 5
...
exit code: 0

$ uv run python scripts/dispatch_sdd_task.py --feature 2026-06-09-executable-harness-hard-cut --task 8 --mode read-only
error: task is already complete and cannot be dispatched: Task 8 — SDD dry-run dispatch CLI
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_tasks_reject_invalid_coordination_field_values tests/architecture/test_sdd_artifact_validator.py::test_tasks_allow_explicit_none_dependency_and_not_delegated_handoff -q
2 passed in 0.02s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_ignores_old_success_outside_verification_commands tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_skipped_table_to_match_skip_count -q
2 passed in 0.02s
exit code: 0

$ uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_work_index_renders_task_dispatch_board -q
1 passed in 0.01s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_tasks_reject_unresolved_dependencies tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_dispatch_cli_refuses_unmet_dependencies tests/architecture/test_agent_playbook_contracts.py::test_sdd_work_index_renders_task_dispatch_board -q
3 passed in 0.05s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py tests/architecture/test_agent_playbook_contracts.py -q
26 passed in 0.59s
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py --check
SDD artifact validation passed.
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ uv run ruff check scripts/validate_sdd_artifacts.py scripts/dispatch_sdd_task.py scripts/regen_sdd_work_index.py tests/architecture/test_sdd_artifact_validator.py tests/architecture/test_agent_playbook_contracts.py
All checks passed!
exit code: 0

$ uv run pytest tests/architecture -m architecture -q
381 passed, 1 skipped in 103.08s
exit code: 0

$ uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_accepts_evidence_report tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_rejects_unverifiable_or_out_of_scope_report tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_accepts_task_bound_report tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_rejects_task_bound_scope_and_command_drift tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_dispatch_cli_emits_handoff_for_in_progress_task -q
5 passed in 0.17s
exit code: 0

$ uv run pytest tests/architecture/test_agent_playbook_contracts.py tests/architecture/test_sdd_artifact_validator.py -q
30 passed in 0.37s
exit code: 0

$ uv run ruff check scripts/validate_subagent_report.py scripts/dispatch_sdd_task.py tests/architecture/test_agent_playbook_contracts.py
All checks passed!
exit code: 0

$ uv run pytest tests/architecture -m architecture -q
385 passed, 1 skipped in 99.84s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_review_evidence_fields tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_reject_invalid_review_evidence_values tests/architecture/test_agent_playbook_contracts.py::test_tasks_template_has_parallel_subagent_contract_fields tests/architecture/test_agent_playbook_contracts.py::test_sdd_work_index_renders_task_dispatch_board -q
4 passed in 0.04s
exit code: 0

$ uv run pytest tests/architecture/test_agent_playbook_contracts.py tests/architecture/test_sdd_artifact_validator.py -q
32 passed in 0.33s
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py --check
SDD artifact validation passed.
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ uv run ruff check scripts/validate_sdd_artifacts.py scripts/regen_sdd_work_index.py tests/architecture/test_sdd_artifact_validator.py tests/architecture/test_agent_playbook_contracts.py
All checks passed!
exit code: 0

$ uv run pytest tests/architecture -m architecture -q
387 passed, 1 skipped in 104.76s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_report_artifact tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_validate_report_artifact_against_task tests/architecture/test_agent_playbook_contracts.py::test_subagent_report_validator_accepts_task_bound_report -q
3 passed in 0.05s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py -q
14 passed in 0.12s
exit code: 0

$ uv run pytest tests/architecture/test_test_lane_contracts.py -q
5 passed in 0.23s
exit code: 0

$ uv run pytest tests/unit/domains/macro_intel/test_macro_migration_contract.py -q
10 passed in 0.16s
exit code: 0

$ uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_context_packet_cli -q
1 passed in 0.07s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_complete_tasks_require_matching_verification_evidence tests/architecture/test_agent_playbook_contracts.py::test_context_packet_cli -q
2 passed in 0.05s
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py --check
SDD artifact validation passed.
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py tests/architecture/test_agent_playbook_contracts.py -q
35 passed in 0.36s
exit code: 0

$ uv run ruff check scripts/validate_sdd_artifacts.py scripts/regen_sdd_work_index.py tests/architecture/test_sdd_artifact_validator.py tests/architecture/test_agent_playbook_contracts.py
All checks passed!
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_non_delegated_handoff_rejects_prose_suffix tests/architecture/test_sdd_artifact_validator.py::test_tasks_allow_explicit_none_dependency_and_not_delegated_handoff tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_report_artifact -q
3 passed in 0.02s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_handoff_artifact tests/architecture/test_sdd_artifact_validator.py::test_delegated_tasks_require_report_artifact -q
2 passed in 0.02s
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_feature_rejects_mixed_artifact_statuses -q
F                                                                        [100%]
AssertionError: assert 'artifact-status-mismatch' in set()
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_feature_rejects_mixed_artifact_statuses -q
1 passed in 0.01s
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py --check
SDD artifact validation passed.
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py tests/architecture/test_agent_playbook_contracts.py -q
38 passed in 0.53s
exit code: 0

$ uv run ruff check scripts/validate_sdd_artifacts.py scripts/regen_sdd_work_index.py tests/architecture/test_sdd_artifact_validator.py tests/architecture/test_agent_playbook_contracts.py
All checks passed!
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_superseded_feature_requires_machine_readable_successor -q
F                                                                        [100%]
AssertionError: assert 'superseded-missing-successor' in set()
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_superseded_feature_requires_machine_readable_successor -q
1 passed in 0.01s
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py --check
SDD artifact validation passed.
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py tests/architecture/test_agent_playbook_contracts.py -q
39 passed in 0.44s
exit code: 0

$ uv run ruff check scripts/validate_sdd_artifacts.py scripts/regen_sdd_work_index.py tests/architecture/test_sdd_artifact_validator.py tests/architecture/test_agent_playbook_contracts.py
All checks passed!
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_feature_rejects_unexpected_artifact_files -q
F                                                                        [100%]
AssertionError: assert 'unexpected-artifact' in set()
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_feature_rejects_unexpected_artifact_files -q
1 passed in 0.02s
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py --check
error: unexpected-artifact: docs/sdd/features/completed/2026-06-09-macro-intel-redesign/macro-actual-assets-desktop.png: feature directories must contain only spec.md, plan.md, tasks.md, verification.md
...
error: unexpected-artifact: docs/sdd/features/completed/2026-06-09-macro-intel-redesign/timsun-assets-comparison.txt: feature directories must contain only spec.md, plan.md, tasks.md, verification.md
exit code: 1

$ uv run python scripts/validate_sdd_artifacts.py --check
SDD artifact validation passed.
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py tests/architecture/test_agent_playbook_contracts.py -q
40 passed in 0.48s
exit code: 0

$ uv run ruff check scripts/validate_sdd_artifacts.py scripts/regen_sdd_work_index.py tests/architecture/test_sdd_artifact_validator.py tests/architecture/test_agent_playbook_contracts.py
All checks passed!
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_completed_tasks_reject_incomplete_dependencies -q
F                                                                        [100%]
AssertionError: assert 'task-invalid-dependencies' in set()
exit code: 1

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_completed_tasks_reject_incomplete_dependencies -q
1 passed in 0.01s
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py --check
error: task-invalid-dependencies: docs/sdd/features/active/2026-06-09-executable-harness-hard-cut/tasks.md: Task 6 — Agent factory and eval/repair loop gate complete before dependencies: Task 5
exit code: 1

$ uv run python scripts/validate_sdd_artifacts.py --check
SDD artifact validation passed.
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ uv run pytest tests/architecture/test_sdd_artifact_validator.py tests/architecture/test_agent_playbook_contracts.py -q
41 passed in 0.40s
exit code: 0

$ uv run ruff check scripts/validate_sdd_artifacts.py scripts/regen_sdd_work_index.py tests/architecture/test_sdd_artifact_validator.py tests/architecture/test_agent_playbook_contracts.py
All checks passed!
exit code: 0
```

## Diff summary

Files changed:

- SDD executable harness: `scripts/validate_sdd_artifacts.py`, `scripts/dispatch_sdd_task.py`, `scripts/validate_subagent_report.py`, `scripts/regen_sdd_work_index.py`, SDD templates, `docs/generated/sdd-work-index.md`.
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
