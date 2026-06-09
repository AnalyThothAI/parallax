# Plan — Executable Harness Hard Cut

**Status**: In Progress
**Date**: 2026-06-09
**Owning spec**: `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut/spec.md`
**Worktree**: `.worktrees/agent-factory-eval-harness`
**Branch**: `codex/agent-factory-eval-harness`
**Approved by**: qinghuan
**Approved at**: 2026-06-09

## Pre-flight

- [x] Spec is approved by delegated user goal.
- [x] Worktree exists at `.worktrees/executable-harness-hard-cut` and `git branch --show-current` matches `codex/executable-harness-hard-cut`.
- [ ] Baseline `uv run ruff check .` passes.
- [ ] Baseline `uv run pytest` passes or known failures are listed in verification.

Known-failing baseline tests:

- None accepted without verification evidence.

## File-level edits

### `scripts/validate_sdd_artifacts.py`

- Create a pure filesystem validator with `scan_sdd_features(root: Path)`, `validate_sdd_root(root: Path)`, and a `--check` CLI.
- Emit deterministic issue codes for missing gate sections, missing approval metadata, incomplete task fields, false `Verified` evidence, stale generated index, and active touch/conflict overlap.
- Validate task field semantics, not just presence: path-shaped file/touch values, structured conflict rules, command-shaped verification, test-shaped failing-test-first values, and known task status tokens.
- Parse `Verified` completion evidence from the `## Verification commands` fenced block and require final `make check-all` exit code 0 plus explained skipped-test rows.

### `scripts/regen_sdd_work_index.py`

- Replace artifact-only rows with feature-level summaries and a coordination board.
- Reuse the validator metadata rather than duplicating SDD parsing rules.

### `scripts/build_agent_context_packet.py`

- Add a pure filesystem CLI that validates SDD records, selects one active feature task, and renders a bounded
  subagent context packet from the task's coordination and agent-loop fields.
- Keep it development-harness only; do not create a product LLM task queue, persistent runtime state, or compatibility
  path for old planning records.

### `scripts/dispatch_sdd_task.py`

- Add a pure filesystem dry-run dispatcher that validates SDD records, selects one active feature task, refuses
  completed or non-dispatchable task statuses, and renders a subagent handoff containing the generated context packet.
- Keep dispatch non-persistent for this slice; no task claiming table, product agent queue, or runtime side effect.

### `tests/architecture/test_agent_playbook_contracts.py`

- Update generated-index assertions from string counters to semantic coordination-board requirements.
- Require the SDD validator to pass as part of the architecture harness.
- Require explicit development-agent factory and eval/repair loop playbook contracts.
- Require the context-packet CLI to build a bounded packet from an active SDD task.
- Require the dry-run dispatch CLI to emit a handoff for in-progress tasks and refuse completed tasks.

### `tests/architecture/test_sdd_artifact_validator.py`

- Add fixture tests for invalid task coordination field values and valid explicit `none` dependencies / `not delegated` handoffs.
- Add fixture tests proving old successful `make check-all` snippets outside the canonical verification block do not satisfy `Verified`.

### `tests/architecture/test_test_lane_contracts.py`

- Add taxonomy checks for permanent invariants, migration tripwires, behavior contracts, and generated hygiene.

### `docs/agent-playbook/factory-operating-model.md`

- Codify development-agent lanes as bounded factory lanes, separate from product LLM agents.
- Split deterministic constraints from on-demand context so subagents receive small, precise packets.
- Define parent integrator ownership, maximum lane count, and kill/defer criteria.
- Route subagent handoffs through `scripts/build_agent_context_packet.py` instead of hand-copying template prose.
- Route dispatch prompts through `scripts/dispatch_sdd_task.py` so completed tasks are not handed off again.

### `docs/agent-playbook/eval-repair-loop.md`

- Define trace datasets, review defects, harness failures, token cost, and repair-loop closeout evidence.
- Require verification evidence before any production claim.

### `tests/support/query_contract.py`

- Create a lightweight SQL contract assertion helper that normalizes SQL and supports required tables, forbidden tables, required predicates, forbidden fragments, required locks, and params.

### `tests/unit/domains/macro_intel/test_macro_migration_contract.py`

- Replace the obsolete `concept_history_counts` raw-fact assertion with a projected-row request-path contract using the query-contract helper.

### `src/parallax/domains/macro_intel/repositories/macro_intel_repository.py`

- Update `concept_history_counts` to read `macro_observation_series_rows` for request-path history counts.

### `Makefile`

- Add `uv run python scripts/validate_sdd_artifacts.py --check` and keep `uv run python scripts/regen_sdd_work_index.py --check` in `check-all`.

### `docs/sdd/_templates/*.md`, `docs/WORKFLOW.md`, `docs/sdd/README.md`

- Add machine-readable approval, gate, worktree, touch set, conflict set, analysis, and verification metadata expected by the validator.
- Add factory lane, deterministic constraints, on-demand context, kill/defer criteria, and eval/repair signal fields to task records.

## PR breakdown

1. **PR 1 — executable SDD harness**: scripts, templates, generated index, architecture tests, Makefile.
2. **PR 2 — SQL contract and macro obsolete test removal**: query helper, macro repository/test update.

This branch implements both slices together because the user requested a thorough hard cut in one pass.

## Rollout order

1. Write failing tests for SDD validator/index/query contract behavior.
2. Implement validator and index generator changes.
3. Regenerate `docs/generated/sdd-work-index.md`.
4. Refactor macro request-path test and implementation.
5. Run focused tests, then broad gates.

## Rollback

This is a development harness hard cut. Rollback is reverting this branch before merge. After merge, false positives should be fixed by adjusting the validator with tests, not by preserving legacy compatibility paths.

## Analyze Gate

| Check | Result |
|-------|--------|
| Spec goals map to plan edits. | Pass: G1-G5 map to script, generated index, tests, query helper, and Makefile edits. |
| Product runtime boundary is untouched. | Pass: no product LLM runtime or queue changes planned. |
| Compatibility paths are removed rather than wrapped. | Pass: no retired planning-lane support planned. |
| Multi-agent coordination is represented as metadata. | Pass: owner/worktree/branch/touch/conflict/review fields are planned. |
| Development-agent loops are separated from product agents. | Pass: factory/eval playbooks explicitly keep product LLM agents outside development-agent lanes. |
| Context packets are executable, not prose-only. | Pass: a new CLI reads active SDD task metadata and emits a bounded handoff packet. |
| Dispatch is dry-run and non-runtime. | Pass: dispatcher emits prompts only and refuses completed tasks without creating durable product state. |
| Task fields are semantically checked. | Pass: validator rejects `none` touch sets, non-command verification, non-test failing-test-first values, and unknown task statuses. |
| Verified evidence is replayable. | Pass: validator reads the canonical command block and validates skipped-test table rows. |

## Acceptance test commands

- AC1: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_successful_make_check_all_evidence -q`
- AC2: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_tasks_require_filled_coordination_fields -q`
- AC3: `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_work_index_is_generated_and_current -q`
- AC4: `uv run pytest tests/unit/domains/macro_intel/test_macro_migration_contract.py::test_repository_concept_history_counts_reads_projected_rows -q`
- AC5: `make check-all`
- AC6: `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_development_agent_factory_model_is_explicit_and_bounded tests/architecture/test_agent_playbook_contracts.py::test_development_agent_eval_repair_loop_is_defined -q`
- AC7: `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_context_packet_cli -q`
- AC8: `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_dispatch_cli_emits_handoff_for_in_progress_task tests/architecture/test_agent_playbook_contracts.py::test_sdd_task_dispatch_cli_refuses_completed_task -q`
- AC9: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_tasks_reject_invalid_coordination_field_values tests/architecture/test_sdd_artifact_validator.py::test_tasks_allow_explicit_none_dependency_and_not_delegated_handoff -q`
- AC10: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_ignores_old_success_outside_verification_commands tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_skipped_table_to_match_skip_count -q`

## Verification

Verification evidence lives in `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut/verification.md`.
