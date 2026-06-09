# Verification - SDD Governance Hard Cut

**Status**: Superseded
**Date**: 2026-06-09
**Owning spec**: `docs/sdd/features/completed/2026-06-09-sdd-governance-hard-cut/spec.md`
**Owning plan**: `docs/sdd/features/completed/2026-06-09-sdd-governance-hard-cut/plan.md`
**Branch**: `codex/sdd-v2-hard-cut`
**Worktree**: `.worktrees/sdd-v2-hard-cut/`
**Approved by**: qinghuan
**Approved at**: 2026-06-09
**Superseded by**: `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut/`

## Spec Compliance

| Acceptance criterion | Status | Evidence |
|----------------------|--------|----------|
| AC1 | Verified | `make check` passed architecture tests including `test_harness_structure.py`. The legacy planning tree absence check printed `docs-superpowers-removed`. |
| AC2 | Verified | `uv run python scripts/regen_sdd_work_index.py --check` passed; generated index reports zero `missing-status` and zero `review-lifecycle`. |
| AC3 | Verified | `make docs-generated` passed and regenerated `docs/generated/sdd-work-index.md`; old generated work index remains deleted. |
| AC4 | Verified | `make check` passed `test_agent_playbook_contracts.py`; legacy name audit found no old router or generator references. |

## Verification Commands

- `make docs-generated` passed.
- `make check` passed: Python ruff, format check, mypy, frontend typecheck/lint/architecture/format, unit, architecture, contract, and compileall. Pytest summary: `2616 passed, 3 skipped`.
- `uv run python scripts/regen_sdd_work_index.py --check` passed.
- Legacy planning tree absence check printed `docs-superpowers-removed`.
- Legacy path, generated-index, and generator-name audit returned no matches across current governance, docs, scripts, tests, `Makefile`, and `pyproject.toml`.
- `git diff --check` passed.

## Coverage

The verification covers the documentation harness, generated SDD index, router mirroring, frontend architecture harness, Python unit tests, architecture tests, contract tests, and compileall.

## Skipped Tests

Per operator instruction on 2026-06-09, the long `make check-all` run was stopped during `tests/integration`; integration, e2e, golden, and coverage gates were not used as final evidence for this documentation-harness hard cut.

## E2E Golden Path

Not applicable to this documentation-harness change unless broader verification requires it.

## Risks Observed

- Historical planning docs are deeply cross-linked. The mitigation is deletion plus a current-governance path scan, not path compatibility.
