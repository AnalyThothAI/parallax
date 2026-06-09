# Spec - SDD Governance Hard Cut

**Status**: Superseded
**Date**: 2026-06-09
**Owner**: Codex
**Related**: `docs/WORKFLOW.md`, `docs/TESTING.md`, `AGENTS.md`, `CLAUDE.md`
**Superseded by**: `docs/sdd/features/active/2026-06-09-executable-harness-hard-cut/`

## Background

The repository previously used a legacy superpowers planning tree and generated an agent work index from those files. The lane had hundreds of historical planning artifacts, many active files with completion-like statuses, and many files without a status line. `docs/WORKFLOW.md` and `docs/TESTING.md` define completion gates, while `tests/architecture/test_harness_structure.py` and `tests/architecture/test_agent_playbook_contracts.py` enforce the documentation harness.

## Problem

The old lane made stale planning artifacts look current and caused `missing-status` and `review-lifecycle` hygiene debt to accumulate. Agent instructions also pointed coding agents at historical docs that should not be treated as live product truth.

## First Principles

- Canonical runtime truth lives in code, database facts, root governance docs, domain architecture maps, tests, and generated contracts.
- SDD artifacts are feature-local execution records, not a parallel documentation archive.
- Completion evidence is mechanical: tests and generated docs must prevent old lanes and stale lifecycle states from returning.

## Goals

- G1. Remove the legacy superpowers planning tree and all current governance references to it.
- G2. Replace it with a compact `docs/sdd` feature-directory workflow aligned with spec-driven development.
- G3. Replace the old agent work index with `sdd-work-index.md` and make `missing-status` and `review-lifecycle` both zero.
- G4. Keep `AGENTS.md` and `CLAUDE.md` router blocks mirrored.

## Non-goals

- N1. Preserve compatibility aliases for old documentation paths.
- N2. Rewrite product architecture or runtime code.
- N3. Retain historical planning artifacts as a new archive.

## Target Architecture

`docs/sdd` owns only current SDD mechanics: templates and feature directories under `features/active` and `features/completed`. A generator scans the feature directories and emits a compact hygiene index. Architecture tests assert that the old lane is absent, current governance does not reference it, templates include required completion sections, and generated docs are clean.

## Acceptance Criteria

- AC1. WHEN the harness tests run THEN the system SHALL fail if the legacy planning tree exists or current governance references its old path.
- AC2. WHEN `uv run python scripts/regen_sdd_work_index.py --check` runs THEN the committed `docs/generated/sdd-work-index.md` SHALL be current and report zero `missing-status` and zero `review-lifecycle`.
- AC3. WHEN `make docs-generated` runs THEN generated docs SHALL not recreate the old work index or old SDD path references.
- AC4. WHEN `AGENTS.md` or `CLAUDE.md` is inspected THEN their shared router blocks SHALL match and point to `docs/sdd`.

## Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| Canonical docs still cite deleted historical files. | High | Add architecture scan for legacy path strings. |
| Generated docs drift back to old names. | High | Rename generator and update `make docs-generated` plus integration expectations. |
| Completed artifacts lose status hygiene. | Medium | Generate an index that flags missing status in every artifact. |

## Boundaries

| Class | Behaviour |
|-------|-----------|
| Always | Delete old planning docs and update current governance/tests/scripts. |
| Ask first | Runtime architecture changes outside documentation harness. |
| Never | Add compatibility aliases or keep old path references in current governance. |
