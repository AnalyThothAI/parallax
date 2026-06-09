# Plan — Executable Harness Hard Cut

**Status**: In Progress
**Date**: 2026-06-09
**Owning spec**: `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut/spec.md`
**Worktree**: `.worktrees/executable-harness-hard-cut`
**Branch**: `codex/executable-harness-hard-cut`
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

### `scripts/regen_sdd_work_index.py`

- Replace artifact-only rows with feature-level summaries and a coordination board.
- Reuse the validator metadata rather than duplicating SDD parsing rules.

### `tests/architecture/test_agent_playbook_contracts.py`

- Update generated-index assertions from string counters to semantic coordination-board requirements.
- Require the SDD validator to pass as part of the architecture harness.

### `tests/architecture/test_test_lane_contracts.py`

- Add taxonomy checks for permanent invariants, migration tripwires, behavior contracts, and generated hygiene.

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

## Acceptance test commands

- AC1: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_verified_feature_requires_successful_make_check_all_evidence -q`
- AC2: `uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_tasks_require_filled_coordination_fields -q`
- AC3: `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_sdd_work_index_is_generated_and_current -q`
- AC4: `uv run pytest tests/unit/domains/macro_intel/test_macro_migration_contract.py::test_repository_concept_history_counts_reads_projected_rows -q`
- AC5: `make check-all`

## Verification

Verification evidence lives in `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut/verification.md`.
