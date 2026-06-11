# Verification — Agent Playbook Skill Hard Cut

**Status**: In Progress
**Date**: 2026-06-09
**Owning spec**: `docs/sdd/features/active/2026-06-09-agent-playbook-skill-hard-cut/spec.md`
**Owning plan**: `docs/sdd/features/active/2026-06-09-agent-playbook-skill-hard-cut/plan.md`
**Branch**: `main`
**Worktree**: `main`
**Approved by**: delegated goal
**Approved at**: 2026-06-09
**Diff**: Pending final diff.

The plan and spec are the contract. This file is the evidence the contract was met. No completion claim is allowed without command output below.

## Spec compliance

| Acceptance criterion | Status | Evidence |
|----------------------|--------|----------|
| AC1 — playbook examples and checklist exist. | Pass | `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_agent_playbook_has_task_examples_and_read_model_checklist -q` passed after implementation. |
| AC2 — repo-scoped skills exist. | Pass | `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_repo_scoped_agent_skills_cover_high_frequency_workflows -q` passed after implementation. |
| AC3 — macro history count avoids latest-only filter. | Pass | Targeted macro SQL contract tests passed after implementation. |
| AC4 — generated SDD index reflects the work. | Pass | `uv run python scripts/validate_sdd_artifacts.py` and `uv run python scripts/regen_sdd_work_index.py --check` passed after lifecycle command cleanup. |

Deviations from spec:

- None.

Deviations from plan:

- Work is in the main checkout because the delegated goal explicitly targeted existing main-branch modifications.

## Verification commands

The only command whose output may be pasted as completion evidence is `make check-all`. Paste the full output below, including the exit code line, before moving this feature to `completed`.

```text
$ make check-all
Pending final run.
exit code: pending
```

## Coverage

| metric | value | threshold | status |
|--------|-------|-----------|--------|
| line   | Pending | >= 80% | Fail |
| branch | Pending | >= 70% | Fail |

## Skipped tests

Number of skipped tests in the run above: 0

If the final run skips tests, list categories and explain why each is acceptable.

## E2E golden path

Confirm each runtime signal from the spec was asserted:

- [ ] /readyz returned 200
- [ ] writer wrote a row visible to a separate process
- [ ] /api/recent returned the injected event
- [ ] WS /ws/live pushed within 5s
- [ ] testcontainers PG and uvicorn subprocess cleaned up

## Other commands run

```text
$ uv run pytest tests/architecture/test_agent_playbook_contracts.py -q
..........
10 passed in 0.18s

$ uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_agent_playbook_has_task_examples_and_read_model_checklist -q
1 passed in 0.01s
exit code: 0

$ uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_repo_scoped_agent_skills_cover_high_frequency_workflows -q
1 passed in 0.01s
exit code: 0

$ uv run pytest tests/unit/domains/macro_intel/test_macro_migration_contract.py::test_repository_concept_history_counts_reads_projected_rows tests/unit/domains/macro_intel/test_macro_generation_swap.py::test_observation_series_readers_read_current_rows_directly -q
..
2 passed in 0.20s
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py
SDD artifact validation passed.
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ uv run ruff check tests/architecture/test_agent_playbook_contracts.py tests/unit/domains/macro_intel/test_macro_generation_swap.py tests/unit/domains/macro_intel/test_macro_migration_contract.py src/parallax/domains/macro_intel/repositories/macro_intel_repository.py scripts/validate_sdd_artifacts.py scripts/regen_sdd_work_index.py
All checks passed!
exit code: 0
```

## Diff summary

Files changed:

- `docs/agent-playbook/task-reading-matrix.md`
- `docs/agent-playbook/task-examples.md`
- `docs/agent-playbook/read-model-change-checklist.md`
- `.agents/skills/*/SKILL.md`
- `tests/architecture/test_agent_playbook_contracts.py`
- `src/parallax/domains/macro_intel/repositories/macro_intel_repository.py`
- `tests/unit/domains/macro_intel/test_macro_migration_contract.py`
- `tests/unit/domains/macro_intel/test_macro_generation_swap.py`
- `docs/sdd/features/active/2026-06-09-agent-playbook-skill-hard-cut/*`

Migrations applied:

- None.

Schema or contract changes that consumers must be aware of:

- Macro history counts now count all projected lookback rows instead of latest-only rows.

## Risks observed

- Final `make check-all` has not run yet.

## Follow-ups

- Recommendation 3 from the research document, a real-data secret-safety hook, remains intentionally out of scope.
