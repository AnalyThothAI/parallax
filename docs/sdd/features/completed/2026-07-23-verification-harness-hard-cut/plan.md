# Plan — Verification Harness Hard Cut

**Status**: Verified
**Superseded by**: N/A
**Date**: 2026-07-23
**Owning spec**: `docs/sdd/features/completed/2026-07-23-verification-harness-hard-cut/spec.md`
**Worktree**: `.worktrees/verification-harness-hard-cut/`
**Branch**: `codex/verification-harness-hard-cut`
**Approved by**: user
**Approved at**: 2026-07-23

## Pre-flight

- [x] Spec is approved by the user's direct request.
- [x] Worktree exists at `.worktrees/verification-harness-hard-cut/` and `git branch --show-current` matches `codex/verification-harness-hard-cut`.
- [x] Root checkout user changes are outside this worktree and remain untouched.

Known-failing baseline tests:

- None known in the focused SDD validator test module.

## File-level edits

### Build and dependencies

- Remove the three retired Make targets and their `.PHONY` entries while
  retaining every direct lint, static, and test lane.
- Remove `pytest-cov`, both coverage configuration sections, and regenerated
  lock entries.
- Remove coverage-only exclusion pragmas from current source and tests.

### SDD validator and generator

- Replace the aggregate-command/coverage/skip/E2E checks with one deep
  verification interface: complete spec rows must cite successful recorded
  commands.
- Delete retired issue codes, parsers, constants, and generated work-index
  meanings.
- Keep task completion, acceptance numbering, evidence matching, approvals,
  worktree metadata, and coordination validation.

### Current governance and templates

- Rewrite README, AGENTS/CLAUDE routing, workflow, testing, factory/eval docs,
  SDD docs, and verification template around risk-based direct commands.
- Preserve completed SDDs and review/audit history unchanged.

### Previously blocked SDD

- Replace the active Macro hard-cut record's retired aggregate requirement with
  direct command evidence for all 16 acceptance criteria, pass its verify gate,
  and archive it under `completed`.

### Tests

- Extend `tests/unit/test_validate_sdd_artifacts.py` at the validator interface:
  targeted successful commands pass; missing/non-zero cited evidence fails.

## PR breakdown

1. **PR 1 — verification harness hard cut**: one atomic deletion across build,
   validator, dependency, template, and canonical governance surfaces.

## Analyze Gate

| Check | Result |
|-------|--------|
| Spec goals map to file-level edits. | Pass: build, validator, tests, templates, docs, and Macro SDD closure cover G1-G4. |
| Plan preserves canonical architecture boundaries. | Pass: product/runtime code and direct test lanes are unchanged. |
| Compatibility code or old files are not retained. | Pass: aggregate targets and coverage machinery are deleted without aliases. |
| Parallel touch/conflict sets are explicit. | Pass: the task coordinates Makefile and coverage-only pragma cleanup with backend audit, and router/generated docs with macro hard cut. |

## Rollout order

1. Add failing validator interface tests.
2. Remove aggregate and coverage implementation.
3. Simplify templates and canonical governance.
4. Regenerate lock and SDD work index.
5. Verify and archive the accepted Macro hard-cut SDD.
6. Run focused validation and residual scans.

## Rollback

Revert the single feature commit. No product schema or runtime data changes are
involved.

## Acceptance test commands

- AC1: `make help`
- AC2: `uv run pytest tests/unit/test_validate_sdd_artifacts.py -q`
- AC3: `uv run pytest tests/unit/test_validate_sdd_artifacts.py -q`
- AC4: `uv run python scripts/validate_sdd_artifacts.py`
- AC5: `uv run python scripts/check_sdd_gate.py --feature 2026-07-23-macro-evidence-ai-hard-cut --gate verify`

## Verification

Verification evidence lives in
`docs/sdd/features/completed/2026-07-23-verification-harness-hard-cut/verification.md`.
