# Tasks — Verification Harness Hard Cut

**Status**: Verified
**Superseded by**: N/A
**Owning plan**: `docs/sdd/features/completed/2026-07-23-verification-harness-hard-cut/plan.md`
**Worktree**: `.worktrees/verification-harness-hard-cut/`
**Branch**: `codex/verification-harness-hard-cut`
**Approved by**: user
**Approved at**: 2026-07-23

## Gate Compliance

| Gate | Evidence |
|------|----------|
| Clarify | `spec.md` records the user's direct hard-cut decisions. |
| Checklist | `spec.md` maps each requirement to a focused check. |
| Analyze | `plan.md` maps the one verification seam across implementation surfaces. |
| Implement | The task replaces old evidence rules rather than layering another wrapper. |
| Verify | `verification.md` records direct commands and residual scans. |

## Tasks

### Task 1 — Hard-cut aggregate completion and coverage machinery

- **File(s)**: `Makefile`, `pyproject.toml`, `uv.lock`, `scripts/validate_sdd_artifacts.py`, `scripts/check_sdd_gate.py`, `scripts/regen_sdd_work_index.py`, `src/parallax/integrations/news_feeds/provider_registry.py`, `src/parallax/domains/news_intel/types/news_source_role_rank.py`, `src/parallax/domains/news_intel/runtime/news_item_process_worker.py`, `src/parallax/domains/news_intel/runtime/news_fetch_worker.py`, `tests/unit/test_validate_sdd_artifacts.py`, `tests/unit/domains/news_intel/test_news_provider_contract.py`, `tests/unit/test_token_radar_projection_worker.py`, `tests/unit/test_ops_diagnostics.py`, `AGENTS.md`, `CLAUDE.md`, `README.md`, `docs/WORKFLOW.md`, `docs/TESTING.md`, `docs/DESIGN_DISCIPLINE.md`, `docs/agent-playbook/task-reading-matrix.md`, `docs/agent-playbook/eval-repair-loop.md`, `docs/agent-playbook/factory-operating-model.md`, `docs/sdd/README.md`, `docs/sdd/_templates/README.md`, `docs/sdd/_templates/verification-template.md`, `docs/generated/sdd-work-index.md`, `docs/sdd/features/completed/2026-07-23-macro-evidence-ai-hard-cut`
- **Owner**: parent
- **Depends on**: none
- **Touch set**: `Makefile`, `pyproject.toml`, `uv.lock`, `scripts/validate_sdd_artifacts.py`, `scripts/check_sdd_gate.py`, `scripts/regen_sdd_work_index.py`, `src/parallax/integrations/news_feeds/provider_registry.py`, `src/parallax/domains/news_intel/types/news_source_role_rank.py`, `src/parallax/domains/news_intel/runtime/news_item_process_worker.py`, `src/parallax/domains/news_intel/runtime/news_fetch_worker.py`, `tests/unit/test_validate_sdd_artifacts.py`, `tests/unit/domains/news_intel/test_news_provider_contract.py`, `tests/unit/test_token_radar_projection_worker.py`, `tests/unit/test_ops_diagnostics.py`, `AGENTS.md`, `CLAUDE.md`, `README.md`, `docs/WORKFLOW.md`, `docs/TESTING.md`, `docs/DESIGN_DISCIPLINE.md`, `docs/agent-playbook/task-reading-matrix.md`, `docs/agent-playbook/eval-repair-loop.md`, `docs/agent-playbook/factory-operating-model.md`, `docs/sdd/README.md`, `docs/sdd/_templates/README.md`, `docs/sdd/_templates/verification-template.md`, `docs/generated/sdd-work-index.md`, `docs/sdd/features/completed/2026-07-23-macro-evidence-ai-hard-cut`, `docs/sdd/features/completed/2026-07-23-verification-harness-hard-cut`
- **Conflict set**: coordinate with 2026-07-22-backend-kiss-deep-audit for Makefile and coverage-only pragma cleanup; coordinate with 2026-07-23-macro-evidence-ai-hard-cut for AGENTS.md, CLAUDE.md, docs/DESIGN_DISCIPLINE.md, docs/generated/sdd-work-index.md
- **Failing test first**: `tests/unit/test_validate_sdd_artifacts.py::test_verified_feature_accepts_relevant_commands_without_repository_wide_gate` — proves targeted successful evidence is the verification interface.
- **Subagent handoff**: not delegated
- **Subagent report**: not delegated
- **Review result**: parent-reviewed
- **Implementation**: Delete aggregate Make targets, coverage tooling, fixed evidence rules, and current prose; retain direct test lanes and successful-command-to-criterion validation; close the accepted Macro hard-cut SDD from its recorded evidence.
- **Verification**: `uv run pytest tests/unit/test_validate_sdd_artifacts.py -q`
- **Review owner**: parent
- **Factory lane**: Harness/tests
- **Deterministic constraints**: no aggregate alias, no coverage dependency/config, direct test lanes remain, completed historical records are unchanged.
- **On-demand context**: `docs/WORKFLOW.md`, `docs/TESTING.md`, SDD validator and verification template.
- **Kill/defer criteria**: stop if a direct test lane or command-evidence rejection would be removed.
- **Eval/repair signal**: focused validator failures, live residual count, diff size reduction.
- **Status**: [x]
