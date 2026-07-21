# Tasks — Agent Playbook Skill Hard Cut

**Status**: Superseded
**Superseded by**: `docs/reviews/backend-kiss-architecture-audit-zh-2026-07-21.md`
**Owning plan**: `docs/sdd/features/completed/2026-06-09-agent-playbook-skill-hard-cut/plan.md`
**Worktree**: `main`
**Branch**: `main`
**Approved by**: delegated goal
**Approved at**: 2026-06-09

## Gate Compliance

| Gate | Evidence |
|------|----------|
| Clarify | `spec.md` includes `## Clarifications`. |
| Checklist | `spec.md` includes `## Requirement Checklist`. |
| Analyze | `plan.md` includes `## Analyze Gate`. |
| Implement | Tasks below are TDD ordered. |
| Verify | `verification.md` will capture command output. |

## Tasks

### Task 1 — Playbook artifact guards

- **File(s)**: `tests/architecture/test_agent_playbook_contracts.py`
- **Owner**: parent
- **Depends on**: none
- **Touch set**: `tests/architecture/test_agent_playbook_contracts.py`
- **Conflict set**: coordinate with `2026-06-11-executable-harness-followup` for shared agent playbook tests and generated index; coordinate with `2026-07-21-signal-pulse-hard-cut` for shared generated SDD index.
- **Failing test first**: `tests/architecture/test_agent_playbook_contracts.py::test_agent_playbook_has_task_examples_and_read_model_checklist` — asserts examples/checklist presence before implementation.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: `uv run pytest tests/architecture/test_agent_playbook_contracts.py -q` must fail missing playbook examples and checklist.
- **On-demand context**: `docs/agent-playbook/task-reading-matrix.md`, current architecture playbook tests, active SDD coordination board.
- **Kill/defer criteria**: Stop if the guard becomes a wording-only assertion without a maintained docs artifact.
- **Eval/repair signal**: architecture harness failure and review defects on missing playbook coverage.
- **Implementation**: Add architecture expectations for playbook examples, checklist, and skills.
- **Verification**: `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_agent_playbook_has_task_examples_and_read_model_checklist -q`
- **Review owner**: parent
- **Status**: [x]

### Task 2 — Playbook examples and skills

- **File(s)**: `docs/agent-playbook/task-reading-matrix.md`, `docs/agent-playbook/task-examples.md`, `docs/agent-playbook/read-model-change-checklist.md`, `.agents/skills/*/SKILL.md`
- **Owner**: parent
- **Depends on**: Task 1
- **Touch set**: `docs/agent-playbook`, `.agents/skills`
- **Conflict set**: coordinate with `2026-06-11-executable-harness-followup` for shared agent playbook docs and task-reading matrix.
- **Failing test first**: `tests/architecture/test_agent_playbook_contracts.py::test_repo_scoped_agent_skills_cover_high_frequency_workflows` — asserts the skills are missing before implementation.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Docs/contracts
- **Deterministic constraints**: Repo-scoped skills must name exact reading lanes and verification commands instead of broad advice.
- **On-demand context**: `docs/agent-playbook/task-examples.md`, `docs/agent-playbook/read-model-change-checklist.md`, `.agents/skills/*/SKILL.md`.
- **Kill/defer criteria**: Stop if a skill duplicates router rules broadly or asks agents to print secrets or live config values.
- **Eval/repair signal**: missing skill contract phrases, stale reading matrix links, and recurring prompt/context repair cost.
- **Implementation**: Add current playbook examples, read-model checklist, and four repo-scoped skills.
- **Verification**: `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_repo_scoped_agent_skills_cover_high_frequency_workflows -q`
- **Review owner**: parent
- **Status**: [x]

### Task 3 — Macro history-count hard cut

- **File(s)**: `tests/unit/domains/macro_intel/test_macro_migration_contract.py`, `tests/unit/domains/macro_intel/test_macro_generation_swap.py`, `src/parallax/domains/macro_intel/repositories/macro_intel_repository.py`
- **Owner**: parent
- **Depends on**: Task 1
- **Touch set**: `tests/unit/domains/macro_intel/test_macro_migration_contract.py`, `tests/unit/domains/macro_intel/test_macro_generation_swap.py`, `src/parallax/domains/macro_intel/repositories/macro_intel_repository.py`
- **Conflict set**: coordinate with `2026-06-11-executable-harness-followup` for shared macro repository and migration-contract edits; coordinate with `2026-06-16-macro-decision-console` for shared macro repository and migration-contract edits.
- **Failing test first**: `tests/unit/domains/macro_intel/test_macro_migration_contract.py::test_repository_concept_history_counts_reads_projected_rows` — forbids `series_rank = 1` in history counts.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Domain implementation
- **Deterministic constraints**: Query contracts must forbid latest-only `series_rank = 1` history counts and retired generation lookup paths.
- **On-demand context**: `src/parallax/domains/macro_intel/ARCHITECTURE.md`, macro migration tests, read-model checklist.
- **Kill/defer criteria**: Stop if the request path reintroduces latest-row filtering or raw observation fallback for history counts.
- **Eval/repair signal**: SQL contract failure and review defect on overfit query-shape assertions.
- **Implementation**: Remove the latest-only series-rank filter from `concept_history_counts`.
- **Verification**: `uv run pytest tests/unit/domains/macro_intel/test_macro_migration_contract.py::test_repository_concept_history_counts_reads_projected_rows tests/unit/domains/macro_intel/test_macro_generation_swap.py::test_observation_series_readers_read_current_rows_directly -q`
- **Review owner**: parent
- **Status**: [x]

### Task 4 — SDD index and final gates

- **File(s)**: `docs/sdd/features/completed/2026-06-09-agent-playbook-skill-hard-cut`, `docs/generated/sdd-work-index.md`
- **Owner**: parent
- **Depends on**: Tasks 1-3
- **Touch set**: `docs/sdd/features/completed/2026-06-09-agent-playbook-skill-hard-cut`, `docs/generated/sdd-work-index.md`
- **Conflict set**: coordinate with `2026-06-11-executable-harness-followup` for shared SDD validator requirements and generated index.
- **Failing test first**: `tests/architecture/test_agent_playbook_contracts.py::test_sdd_work_index_is_generated_and_current` — fails until the generated index reflects current SDD records.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Final integration
- **Deterministic constraints**: `uv run python scripts/validate_sdd_artifacts.py` and `uv run python scripts/regen_sdd_work_index.py --check` must pass after both active records are present.
- **On-demand context**: `docs/sdd/features/completed/2026-06-09-agent-playbook-skill-hard-cut`, `docs/sdd/features/active/2026-06-11-executable-harness-followup`, `docs/generated/sdd-work-index.md`.
- **Kill/defer criteria**: Keep the record active if full `make check-all` remains skipped or if active touch conflicts are unresolved.
- **Eval/repair signal**: `task-missing-agent-loop-fields`, `active-touch-conflict`, stale generated index, and missing final verification evidence.
- **Implementation**: Add SDD records and regenerate the SDD index.
- **Verification**: `uv run python scripts/validate_sdd_artifacts.py && uv run python scripts/regen_sdd_work_index.py --check`
- **Review owner**: parent
- **Status**: [~]
