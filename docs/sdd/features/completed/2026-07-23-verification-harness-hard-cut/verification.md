# Verification — Verification Harness Hard Cut

**Status**: Verified
**Superseded by**: N/A
**Date**: 2026-07-23
**Owning spec**: `docs/sdd/features/completed/2026-07-23-verification-harness-hard-cut/spec.md`
**Owning plan**: `docs/sdd/features/completed/2026-07-23-verification-harness-hard-cut/plan.md`
**Branch**: `codex/verification-harness-hard-cut`
**Worktree**: `.worktrees/verification-harness-hard-cut/`
**Approved by**: user
**Approved at**: 2026-07-23
**Diff**: feature commit on `codex/verification-harness-hard-cut` — 37 files
changed.

## Spec compliance

| Acceptance criterion | Status | Evidence |
|----------------------|--------|----------|
| AC1 - Aggregate and coverage interfaces are absent. | Pass | `make help` exited 0 and exposed only the retained direct lanes. |
| AC2 - Relevant direct commands satisfy verification. | Pass | `uv run pytest tests/unit/test_validate_sdd_artifacts.py -q` exited 0. |
| AC3 - Missing or failed evidence fails closed. | Pass | `uv run pytest tests/unit/test_validate_sdd_artifacts.py -q` exited 0. |
| AC4 - Current governance is risk-based. | Pass | `uv run python scripts/validate_sdd_artifacts.py` exited 0 after the current docs and templates were simplified. |
| AC5 - Accepted Macro hard cut is completed. | Pass | `uv run python scripts/check_sdd_gate.py --feature 2026-07-23-macro-evidence-ai-hard-cut --gate verify` exited 0 after all 16 criteria cited successful direct evidence. |

Deviations from spec:

- None.

Deviations from plan:

- None.

## Verification commands

```text
$ make help
check                 run fast lint, format, typecheck, unit, architecture, and contract checks
test-unit             run only tests/unit/
test-integration      run only tests/integration/ (real PostgreSQL boundary)
test-e2e              run only tests/e2e/ (running service boundary)
test-golden           run only tests/golden/ (real Postgres golden corpus)
test-architecture     run only tests/architecture/ (AST/grep checks)
test-contract         run only tests/contract/
exit code: 0

$ uv run pytest tests/unit/test_validate_sdd_artifacts.py -q
......                                                                   [100%]
6 passed in 0.05s
exit code: 0

$ uv run pytest tests/unit/domains/news_intel/test_news_provider_contract.py tests/unit/test_token_radar_projection_worker.py tests/unit/test_ops_diagnostics.py -q
....................................................                     [100%]
52 passed in 13.54s
exit code: 0

$ make check
All checks passed!
817 files already formatted
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py
SDD artifact validation passed.
exit code: 0

$ uv run python scripts/check_sdd_gate.py --feature 2026-07-23-macro-evidence-ai-hard-cut --gate verify
verify gate passed: 2026-07-23-macro-evidence-ai-hard-cut
exit code: 0
```

## Diff summary

- Build surface: removed `check-all`, `check-sdd-completion`, `coverage`,
  `pytest-cov`, coverage configuration, and lock entries.
- SDD seam: reduced verified evidence to complete tasks plus successful direct
  command evidence mapped to every acceptance criterion.
- Source and tests: removed coverage-only exclusion pragmas without changing
  runtime behavior.
- Governance: rewrote current routers, workflow, testing guidance, playbooks,
  SDD templates, and generated issue meanings around risk-selected commands.
- Lifecycle: verified all 16 Macro hard-cut criteria from recorded direct
  evidence and moved that SDD from `active` to `completed`.

## Risks observed

- Root checkout has pre-existing AGENTS/CLAUDE and `docs/agents/` work; this
  isolated worktree does not modify or absorb it.
- Integration, E2E, and golden lanes were not run because this change does not
  alter their product/runtime boundaries.
- Live residual scans found no retired target, dependency/configuration,
  mandatory-policy phrase, or `# pragma: no cover` match. Historical completed
  SDD records were intentionally left unchanged.

## Follow-ups

- None.
