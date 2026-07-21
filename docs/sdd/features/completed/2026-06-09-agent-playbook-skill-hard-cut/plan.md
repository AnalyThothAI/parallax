# Plan — Agent Playbook Skill Hard Cut

**Status**: Superseded
**Superseded by**: `docs/reviews/backend-kiss-architecture-audit-zh-2026-07-21.md`
**Date**: 2026-06-09
**Owning spec**: `docs/sdd/features/completed/2026-06-09-agent-playbook-skill-hard-cut/spec.md`
**Worktree**: `main`
**Branch**: `main`
**Approved by**: delegated goal
**Approved at**: 2026-06-09

## Pre-flight

- [x] Spec is approved by delegated goal.
- [x] Current checkout is `main`; the user explicitly called out main-branch modifications.
- [ ] Baseline `uv run ruff check .` passes.
- [ ] Baseline `uv run pytest` passes or known failures are listed in verification.

Known-failing baseline tests:

- None accepted without verification evidence.

## File-level edits

### `tests/architecture/test_agent_playbook_contracts.py`

- Add tests requiring `docs/agent-playbook/task-examples.md`, `docs/agent-playbook/read-model-change-checklist.md`, and four repo-scoped skills.

### `docs/agent-playbook/task-reading-matrix.md`

- Link to the examples file and read-model checklist.
- Add a `Read Model Change Review` route with required docs, diagnostics, and answer boundaries.

### `docs/agent-playbook/task-examples.md`

- Add copyable task contracts for provider diagnostics, worker backlog, frontend route shell QA, and read-model change review.

### `docs/agent-playbook/read-model-change-checklist.md`

- Add truth-boundary, audit, test, review, and rejection criteria for read-model changes.

### `.agents/skills/*/SKILL.md`

- Add four repo-scoped skills: worker debugging, real-data provider diagnostics, frontend verification, and read-model review.

### `src/parallax/domains/macro_intel/repositories/macro_intel_repository.py`

- Remove the `series_rank = 1` filter from `concept_history_counts`.

### `tests/unit/domains/macro_intel/test_macro_migration_contract.py`
### `tests/unit/domains/macro_intel/test_macro_generation_swap.py`

- Require `concept_history_counts` to read projected rows and forbid `series_rank = 1`.

### `docs/generated/sdd-work-index.md`

- Regenerate after adding this active SDD record.

## PR breakdown

1. **PR 1 — agent playbook hard cut**: docs, skills, tests, macro history-count fix, SDD index.

## Analyze Gate

| Check | Result |
|-------|--------|
| Spec goals map to file-level edits. | Pass: goals map to playbook docs, skills, tests, macro repository, and generated index edits. |
| Plan preserves canonical architecture boundaries. | Pass: development-agent playbooks stay separate from product runtime agents. |
| Compatibility code or old files are not retained. | Pass: retired macro query filtering is removed rather than wrapped. |
| Parallel touch/conflict sets are explicit. | Pass: shared generated index and harness tests are coordinated with the executable harness feature. |

## Rollout order

1. Add failing architecture tests for missing playbook artifacts and skills.
2. Add failing macro SQL contract tests for `series_rank = 1`.
3. Implement docs, skills, and macro query fix.
4. Regenerate SDD index.
5. Run targeted tests, architecture checks, and final gates.

## Rollback

Revert this feature before merge. After merge, fix regressions by updating the skills/checklists/tests with a new SDD record rather than keeping compatibility paths.

## Acceptance test commands

- AC1: `uv run pytest tests/architecture/test_agent_playbook_contracts.py -q`
- AC2: `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_repo_scoped_agent_skills_cover_high_frequency_workflows -q`
- AC3: `uv run pytest tests/unit/domains/macro_intel/test_macro_migration_contract.py::test_repository_concept_history_counts_reads_projected_rows tests/unit/domains/macro_intel/test_macro_generation_swap.py::test_observation_series_readers_read_current_rows_directly -q`
- AC4: `uv run python scripts/regen_sdd_work_index.py --check`

## Verification

Verification evidence lives in `docs/sdd/features/completed/2026-06-09-agent-playbook-skill-hard-cut/verification.md`.
