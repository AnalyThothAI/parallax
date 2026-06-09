# Tasks - SDD Governance Hard Cut

**Status**: In Progress
**Owning plan**: `docs/sdd/features/active/2026-06-09-sdd-governance-hard-cut/plan.md`
**Worktree**: `.worktrees/sdd-v2-hard-cut/`

## Tasks

- [x] Add failing harness tests for the new `docs/sdd` root and removed legacy planning lane.
- [x] Add failing generated-doc expectations for `sdd-work-index.md`.
- [ ] Create `docs/sdd` templates and feature artifacts.
- [ ] Rename and rewrite the work-index generator.
- [ ] Update root docs, scripts, and architecture tests to the new lane.
- [ ] Delete old historical planning docs and old generated index.
- [ ] Regenerate docs and run targeted verification.
- [ ] Move this feature directory to `completed/` after final verification evidence is recorded.

## Final Verification

- [ ] `make docs-generated`
- [ ] `uv run pytest tests/architecture/test_harness_structure.py tests/architecture/test_agent_playbook_contracts.py tests/architecture/test_completion_gates.py -q`
- [ ] `uv run python scripts/regen_sdd_work_index.py --check`
- [ ] Broader goal audit for old path references and status flags.
