# Plan - SDD Governance Hard Cut

**Status**: In Progress
**Date**: 2026-06-09
**Owning spec**: `docs/sdd/features/active/2026-06-09-sdd-governance-hard-cut/spec.md`
**Worktree**: `.worktrees/sdd-v2-hard-cut/`
**Branch**: `codex/sdd-v2-hard-cut`

## File-Level Edits

- `tests/architecture/test_harness_structure.py`: assert `docs/sdd` structure, absence of the legacy planning tree, and absence of old path references.
- `tests/architecture/test_agent_playbook_contracts.py`: point template and generated-index checks at `docs/sdd` and `scripts/regen_sdd_work_index.py`.
- `tests/architecture/test_completion_gates.py`: point verification-template checks at `docs/sdd/_templates`.
- `tests/integration/test_docs_generated.py`: expect `sdd-work-index.md` instead of the old work-index file.
- `docs/sdd/**`: add templates and this feature record.
- `scripts/regen_sdd_work_index.py`: scan feature directories and emit zero-count lifecycle flags when clean.
- `Makefile` and `docs/generated/README.md`: include the SDD index in generated-docs regeneration.
- `AGENTS.md`, `CLAUDE.md`, and root governance docs: replace old planning-lane references with the SDD v2 lane.
- Delete the legacy planning tree, old work-index generator, and old generated work-index file.

## Acceptance Test Commands

- AC1: `uv run pytest tests/architecture/test_harness_structure.py -q`
- AC2: `uv run python scripts/regen_sdd_work_index.py --check`
- AC3: `uv run pytest tests/integration/test_docs_generated.py::test_expected_generated_files -q`
- AC4: `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_router_shared_blocks_match_and_reference_agent_playbook -q`

## Rollout

This is a repository-governance hard cut. No runtime migration is required.

## Rollback

Rollback is git-only. Do not add compatibility aliases for the deleted lane.
