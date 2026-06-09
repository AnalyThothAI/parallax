# Tasks - SDD Governance Hard Cut

**Status**: Verified
**Owning plan**: `docs/sdd/features/completed/2026-06-09-sdd-governance-hard-cut/plan.md`
**Worktree**: `.worktrees/sdd-v2-hard-cut/`

## Tasks

- [x] Add failing harness tests for the new `docs/sdd` root and removed legacy planning lane.
- [x] Add failing generated-doc expectations for `sdd-work-index.md`.
- [x] Create `docs/sdd` templates and feature artifacts.
- [x] Rename and rewrite the work-index generator.
- [x] Update root docs, scripts, and architecture tests to the new lane.
- [x] Delete old historical planning docs and old generated index.
- [x] Regenerate docs and run targeted verification.
- [x] Move this feature directory to `completed/` after final verification evidence is recorded.

## Final Verification

- [x] `make docs-generated`
- [x] `make check`
- [x] `uv run python scripts/regen_sdd_work_index.py --check`
- [x] Broader goal audit for old path references and status flags.
