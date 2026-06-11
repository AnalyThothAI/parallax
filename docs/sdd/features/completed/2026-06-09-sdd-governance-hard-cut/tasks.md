# Tasks - SDD Governance Hard Cut

**Status**: Superseded
**Owning plan**: `docs/sdd/features/completed/2026-06-09-sdd-governance-hard-cut/plan.md`
**Worktree**: `.worktrees/sdd-v2-hard-cut/`
**Branch**: `codex/sdd-v2-hard-cut`
**Approved by**: qinghuan
**Approved at**: 2026-06-09
**Superseded by**: `docs/sdd/features/active/2026-06-11-executable-harness-followup/`

## Gate Compliance

| Gate | Evidence |
|------|----------|
| Clarify | Superseded spec records the successor and historical-scope clarification. |
| Checklist | Superseded spec keeps the current requirement checklist table. |
| Analyze | Superseded plan records the successor-owned Analyze Gate. |
| Implement | Historical tasks remain structured and marked `[!]` because successor work owns the live implementation. |
| Verify | Verification artifact retains historical evidence without claiming current completion. |

## Tasks

### Task 1 - SDD root and legacy-lane harness

- **File(s)**: `tests/architecture/test_harness_structure.py`, `docs/sdd`
- **Owner**: parent
- **Depends on**: none
- **Touch set**: `tests/architecture/test_harness_structure.py`, `docs/sdd`
- **Conflict set**: `docs/sdd/features/active/2026-06-11-executable-harness-followup`
- **Failing test first**: `tests/architecture/test_harness_structure.py::test_legacy_superpowers_tree_is_removed` - asserts the old planning lane is gone.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Harness/tests
- **Deterministic constraints**: SDD root shape and legacy-lane deletion are architecture-test invariants.
- **On-demand context**: `docs/WORKFLOW.md`, `docs/TESTING.md`, `tests/architecture/test_harness_structure.py`.
- **Kill/defer criteria**: Stop if the old lane must be retained as a compatibility archive.
- **Eval/repair signal**: missing SDD root, legacy path hits, or architecture-test failure.
- **Implementation**: Add failing harness tests for the new `docs/sdd` root and removed legacy planning lane.
- **Verification**: `uv run pytest tests/architecture/test_harness_structure.py -q`
- **Review owner**: parent
- **Status**: [!]

### Task 2 - SDD templates and generated index

- **File(s)**: `docs/sdd/_templates`, `scripts/regen_sdd_work_index.py`, `docs/generated/sdd-work-index.md`, `tests/architecture/test_agent_playbook_contracts.py`
- **Owner**: parent
- **Depends on**: Task 1
- **Touch set**: `docs/sdd/_templates`, `scripts/regen_sdd_work_index.py`, `docs/generated/sdd-work-index.md`, `tests/architecture/test_agent_playbook_contracts.py`
- **Conflict set**: `docs/sdd/features/active/2026-06-11-executable-harness-followup`
- **Failing test first**: `tests/architecture/test_agent_playbook_contracts.py::test_sdd_work_index_is_generated_and_current` - asserts generated index freshness.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Docs/contracts
- **Deterministic constraints**: Generated SDD index must be rebuilt by script and checked in.
- **On-demand context**: `docs/sdd/_templates`, `scripts/regen_sdd_work_index.py`.
- **Kill/defer criteria**: Stop if the generated board duplicates parser rules instead of reusing validator metadata.
- **Eval/repair signal**: stale generated index or template contract failure.
- **Implementation**: Create `docs/sdd` templates, feature artifacts, and the replacement work-index generator.
- **Verification**: `uv run python scripts/regen_sdd_work_index.py --check`
- **Review owner**: parent
- **Status**: [!]

### Task 3 - Governance hard cut

- **File(s)**: `AGENTS.md`, `CLAUDE.md`, `docs/WORKFLOW.md`, `docs/TESTING.md`, `Makefile`, `docs/generated/README.md`
- **Owner**: parent
- **Depends on**: Task 2
- **Touch set**: `AGENTS.md`, `CLAUDE.md`, `docs/WORKFLOW.md`, `docs/TESTING.md`, `Makefile`, `docs/generated/README.md`
- **Conflict set**: `docs/sdd/features/active/2026-06-11-executable-harness-followup`
- **Failing test first**: `tests/architecture/test_agent_playbook_contracts.py::test_router_shared_blocks_match_and_reference_agent_playbook` - asserts router and SDD references.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Docs/contracts
- **Deterministic constraints**: Root routers stay mirrored and current governance must not cite the deleted lane.
- **On-demand context**: `AGENTS.md`, `CLAUDE.md`, `docs/WORKFLOW.md`, `docs/TESTING.md`.
- **Kill/defer criteria**: Stop if compatibility aliases or old path references are required.
- **Eval/repair signal**: router mirror failure, legacy path hits, or generated-doc drift.
- **Implementation**: Update root docs, scripts, architecture tests, generated docs, and delete old historical planning docs.
- **Verification**: `make docs-generated`
- **Review owner**: parent
- **Status**: [!]

### Task 4 - Closeout evidence

- **File(s)**: `docs/sdd/features/completed/2026-06-09-sdd-governance-hard-cut/verification.md`, `docs/sdd/features/completed/2026-06-09-sdd-governance-hard-cut/tasks.md`
- **Owner**: parent
- **Depends on**: Tasks 1-3
- **Touch set**: `docs/sdd/features/completed/2026-06-09-sdd-governance-hard-cut`
- **Conflict set**: `docs/sdd/features/active/2026-06-11-executable-harness-followup`
- **Failing test first**: `tests/architecture/test_harness_structure.py::test_current_governance_does_not_reference_legacy_superpowers_paths` - asserts no legacy path references remain.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Factory lane**: Final integration
- **Deterministic constraints**: Completion record keeps real verification evidence and does not claim integration/e2e gates.
- **On-demand context**: `docs/sdd/features/completed/2026-06-09-sdd-governance-hard-cut/verification.md`.
- **Kill/defer criteria**: Stop if full integration evidence is required but not available.
- **Eval/repair signal**: final validator failure, stale generated index, or missing verification record.
- **Implementation**: Regenerate docs, run targeted verification, and move this feature directory to `completed/` after evidence is recorded.
- **Verification**: `make check`
- **Review owner**: parent
- **Status**: [!]

## Historical closeout notes

- [x] `make docs-generated`
- [x] `make check`
- [x] `uv run python scripts/regen_sdd_work_index.py --check`
- [x] Broader goal audit for old path references and status flags.
