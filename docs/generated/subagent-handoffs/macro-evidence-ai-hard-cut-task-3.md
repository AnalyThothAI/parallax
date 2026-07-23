# Subagent Handoff - 2026-07-23-macro-evidence-ai-hard-cut / Task 3

Mode: write-allowed
Mode constraints:
- Write-allowed mode: changed files must stay inside Owned scope and avoid Do not touch.

Goal:
- Create the concept manifest and deep evidence-snapshot interface; implement pure domain rules and delete the generic score/module implementation.

Owned scope:
- `src/parallax/domains/macro_intel/services/**`
- `src/parallax/domains/macro_intel/_constants.py`
- `tests/unit/domains/macro_intel/**`

Do not touch:
- `src/parallax/domains/macro_intel/runtime/**`
- `src/parallax/domains/macro_intel/repositories/**`
- `src/parallax/app/**`
- `src/parallax/platform/db/**`
- `web/**`
- `docs/generated/**`

Must read:
- `AGENTS.md`
- `docs/agent-playbook/task-reading-matrix.md`
- `src/parallax/domains/macro_intel/ARCHITECTURE.md`
- existing macro service modules end to end
- current observation shapes
- approved Spec domain skeletons

Context packet:

```md
# Context Packet - 2026-07-23-macro-evidence-ai-hard-cut / Task 3

Mode: write-allowed
Mode constraints:
- Write-allowed mode: changed files must stay inside Owned scope and avoid Do not touch.
Factory lane: Domain implementation

Current objective:
- Execute Task 3 for the approved hard cut without expanding the active SDD scope.

Truth boundary:
- Facts: persisted macro observations are the only business truth.
- Read models: one rebuildable six-document snapshot and compact series.
- Control plane: existing macro dirty targets and publication state remain.
- Cache/fan-out: no new cache or generic module catalog.
- Provider raw inputs: not read by this module.

Known symptoms:
- Current macro services build global score/regime/scenario and generic module dictionaries across incompatible frequencies and units.

Canonical docs/code already checked:
- `AGENTS.md` - Kappa/CQRS and no-compat rules.
- `docs/agent-playbook/task-reading-matrix.md` - macro and read-model reading set.
- `src/parallax/domains/macro_intel/ARCHITECTURE.md` - current ownership and projection.
- Existing services and tests - observation shapes and legacy contract.

Relevant active planning artefacts:
- `docs/sdd/features/active/2026-07-23-macro-evidence-ai-hard-cut/spec.md`
- `docs/sdd/features/active/2026-07-23-macro-evidence-ai-hard-cut/plan.md`
- `docs/sdd/features/active/2026-07-23-macro-evidence-ai-hard-cut/tasks.md`

Unknowns:
- Concepts not backed by current observations must remain explicit unavailable evidence.

Redactions:
- Credentials and private runtime values are omitted.

Suggested verification:
- `uv run pytest tests/unit/domains/macro_intel -q`
```

Report contract:
- Use headings: `## Findings`, `## Scope Adherence`, `## Changed Files`, `## Required Reading Evidence`, `## Verification Evidence`, and `## Remaining Risks`.
- Include `Owned scope: pass`, `Conflict set: pass`, and command output with `exit code:`.
- In `## Required Reading Evidence`, include `Task classification:`, `AGENTS.md`, `docs/agent-playbook/task-reading-matrix.md`, and all Task 3 on-demand context.
- Parent validates the report with `uv run python scripts/validate_subagent_report.py --feature 2026-07-23-macro-evidence-ai-hard-cut --task 3 --mode write-allowed --report <report.md>`.

Expected output:
- Findings first with source evidence.
- Changed files inside Owned scope only.
- Exact rule/test coverage and remaining evidence gaps.

Verification evidence:
- `uv run pytest tests/unit/domains/macro_intel -q`

Constraints:
- Work with existing changes; never revert unrelated edits.
- Never print credentials or private runtime values.
- Treat subagent output as evidence, not authority.
