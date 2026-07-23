# Subagent Report - Macro Evidence AI Hard Cut SDD Integrity

Mode: write-allowed

## Findings

- Active SDD records continue to require current repository paths and valid
  path:line evidence. Completed immutable specs still require a syntactically
  valid local or HTTPS citation, but no longer fail when a later approved hard
  cut deletes the historical source file.
- The completed-spec exception is limited to Background citation target
  resolution. Active task path checks, active handoff checks, and active
  subagent report validation remain unchanged and strict.
- The backend KISS active Task 9 inventory no longer claims the three Macro and
  Token files intentionally deleted by this feature as current touch paths.
- Macro hard-cut Tasks 2 and 3 now reference their real validated reports,
  record parent acceptance, and carry successful exact task and failing-test
  command evidence. The Task 2 gate passed 468 tests; the Task 3 gate passed
  203 tests.
- The generated SDD work index was refreshed only through
  `scripts/regen_sdd_work_index.py`.

## Scope Adherence

Owned scope: pass

Conflict set: pass

No production code, migrations, frontend files, completed SDD artifacts, or
canonical runtime documentation were edited. The only test addition exercises
the SDD validator boundary.

## Changed Files

- `scripts/validate_sdd_artifacts.py`
- `tests/unit/test_validate_sdd_artifacts.py`
- `docs/sdd/features/active/2026-07-22-backend-kiss-deep-audit/tasks.md`
- `docs/sdd/features/active/2026-07-23-macro-evidence-ai-hard-cut/tasks.md`
- `docs/sdd/features/active/2026-07-23-macro-evidence-ai-hard-cut/verification.md`
- `docs/generated/sdd-work-index.md`
- `docs/generated/subagent-reports/macro-evidence-ai-hard-cut-sdd-integrity.md`

## Required Reading Evidence

- `docs/WORKFLOW.md`: active-lane mechanics, strict executable records,
  completed-record immutability, generated-index ownership, and completion
  gates.
- `docs/sdd/features/active/2026-07-23-macro-evidence-ai-hard-cut/spec.md`:
  approved AC1-AC16 and the no-compat hard-cut boundary.
- `docs/sdd/features/active/2026-07-23-macro-evidence-ai-hard-cut/plan.md`:
  G1-G8 edit/verification ownership and the Task 2/3 delegation boundary.
- `docs/sdd/features/active/2026-07-23-macro-evidence-ai-hard-cut/tasks.md`:
  exact commands, dependencies, report paths, and review ownership.
- `docs/sdd/features/active/2026-07-23-macro-evidence-ai-hard-cut/verification.md`:
  current evidence and explicitly incomplete final/runtime/browser gates.

## Verification Evidence

```text
$ uv run pytest tests/unit/test_validate_sdd_artifacts.py -q
...                                                                      [100%]
3 passed in 0.03s
exit code: 0

$ uv run ruff check scripts/validate_sdd_artifacts.py tests/unit/test_validate_sdd_artifacts.py
All checks passed!
exit code: 0

$ uv run python scripts/validate_sdd_artifacts.py
SDD artifact validation passed.
exit code: 0

$ uv run python scripts/validate_subagent_report.py --feature 2026-07-23-macro-evidence-ai-hard-cut --task 2 --mode write-allowed --report docs/generated/subagent-reports/macro-evidence-ai-hard-cut-task-2.md
Subagent report validation passed.
exit code: 0

$ uv run python scripts/validate_subagent_report.py --feature 2026-07-23-macro-evidence-ai-hard-cut --task 3 --mode write-allowed --report docs/generated/subagent-reports/macro-evidence-ai-hard-cut-task-3.md
Subagent report validation passed.
exit code: 0

$ uv run python scripts/regen_sdd_work_index.py --check
exit code: 0

$ uv run python scripts/check_sdd_gate.py --feature 2026-07-23-macro-evidence-ai-hard-cut --gate implement
implement gate passed: 2026-07-23-macro-evidence-ai-hard-cut
exit code: 0

$ uv run python scripts/check_sdd_gate.py --all-active
all active SDD gates passed (clarify/checklist/analyze/implement): 2026-07-22-backend-kiss-deep-audit, 2026-07-22-docker-build-contract-fix, 2026-07-22-news-fetch-retention-index, 2026-07-23-macro-evidence-ai-hard-cut
exit code: 0
```

## Remaining Risks

- There are no remaining SDD structural or report-contract blockers.
- Issue #4 is not complete: Task 1 remains in progress, and Tasks 4-8 remain
  open. Projection/migration integration, API/runtime composition, frontend,
  canonical docs/generated contracts, real Docker/browser verification,
  `make check-all`, the zero-skip completion gate, and independent final review
  must still be completed and recorded.
- The operator database remains outside this SDD repair. Revision 0191 must not
  be applied without the approved backup and explicit deployment boundary.
