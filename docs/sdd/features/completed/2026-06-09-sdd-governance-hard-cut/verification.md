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

## Spec compliance

| Acceptance criterion | Status | Evidence |
|----------------------|--------|----------|
| AC1 | Verified | `make check` passed architecture tests including `test_harness_structure.py`. The legacy planning tree absence check printed `docs-superpowers-removed`. |
| AC2 | Verified | `uv run python scripts/regen_sdd_work_index.py --check` passed; generated index reports zero `missing-status` and zero `review-lifecycle`. |
| AC3 | Verified | `make docs-generated` passed and regenerated `docs/generated/sdd-work-index.md`; old generated work index remains deleted. |
| AC4 | Verified | `make check` passed `test_agent_playbook_contracts.py`; legacy name audit found no old router or generator references. |

## Verification commands

```text
$ make docs-generated
passed
exit code: 0

$ make check
Python ruff, format check, mypy, frontend typecheck/lint/architecture/format, unit, architecture, contract, and compileall passed.
Pytest summary: 2616 passed, 3 skipped.
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py --check
passed
exit code: 0

$ git diff --check
passed
exit code: 0
```

## Coverage

The verification covers the documentation harness, generated SDD index, router mirroring, frontend architecture harness, Python unit tests, architecture tests, contract tests, and compileall.

## Skipped tests

Number of skipped tests in the run above: 3

Per operator instruction on 2026-06-09, the long `make check-all` run was stopped during `tests/integration`; integration, e2e, golden, and coverage gates were not used as final evidence for this documentation-harness hard cut.

## E2E golden path

Not applicable to this documentation-harness change unless broader verification requires it.

## Risks Observed

- Historical planning docs are deeply cross-linked. The mitigation is deletion plus a current-governance path scan, not path compatibility.
