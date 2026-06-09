from __future__ import annotations

from pathlib import Path

from scripts.validate_sdd_artifacts import validate_sdd_root


def test_verified_feature_requires_successful_make_check_all_evidence(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "completed", "2026-06-09-false-green")
    _write_valid_spec(feature / "spec.md", status="Verified")
    _write_valid_plan(feature / "plan.md", status="Verified")
    _write_valid_tasks(feature / "tasks.md", status="Verified")
    (feature / "verification.md").write_text(
        "\n".join(
            [
                "# Verification - False Green",
                "",
                "**Status**: Verified",
                "**Date**: 2026-06-09",
                "**Owning spec**: `docs/sdd/features/completed/2026-06-09-false-green/spec.md`",
                "**Owning plan**: `docs/sdd/features/completed/2026-06-09-false-green/plan.md`",
                "**Branch**: `codex/false-green`",
                "**Worktree**: `.worktrees/false-green`",
                "**Approved by**: qinghuan",
                "**Approved at**: 2026-06-09",
                "",
                "## Spec compliance",
                "",
                "All rows marked complete.",
                "",
                "## Verification commands",
                "",
                "```text",
                "$ make check-all",
                "Stopped before completion; not final evidence.",
                "exit code: pending",
                "```",
                "",
                "## Coverage",
                "line coverage pending",
                "",
                "## Skipped tests",
                "Number of skipped tests in the run above: Pending",
                "",
                "## E2E golden path",
                "- [ ] /readyz returned 200",
            ]
        ),
        encoding="utf-8",
    )

    issues = validate_sdd_root(tmp_path)

    assert "verified-missing-check-all" in _issue_codes(issues)
    assert "verified-contradicts-evidence" in _issue_codes(issues)


def test_verified_feature_accepts_successful_make_check_all_evidence(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "completed", "2026-06-09-true-green")
    _write_valid_spec(feature / "spec.md", status="Verified")
    _write_valid_plan(feature / "plan.md", status="Verified")
    _write_valid_tasks(feature / "tasks.md", status="Verified")
    _write_valid_verification(feature / "verification.md", status="Verified")

    assert validate_sdd_root(tmp_path) == []


def test_tasks_require_filled_coordination_fields(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-loose-tasks")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _write_valid_plan(feature / "plan.md", status="In Progress")
    (feature / "tasks.md").write_text(
        "\n".join(
            [
                "# Tasks - Loose",
                "",
                "**Status**: In Progress",
                "**Owning plan**: `docs/sdd/features/active/2026-06-09-loose-tasks/plan.md`",
                "**Worktree**: `.worktrees/loose-tasks`",
                "**Branch**: `codex/loose-tasks`",
                "**Approved by**: qinghuan",
                "**Approved at**: 2026-06-09",
                "",
                "## Gate Compliance",
                "",
                "| Gate | Evidence |",
                "|------|----------|",
                "| Implement | Started. |",
                "",
                "## Tasks",
                "",
                "- [ ] write code",
            ]
        ),
        encoding="utf-8",
    )
    _write_valid_verification(feature / "verification.md", status="In Progress")

    issues = validate_sdd_root(tmp_path)

    assert "task-missing-coordination-fields" in _issue_codes(issues)


def test_active_touch_sets_must_not_overlap_without_conflict_note(tmp_path: Path) -> None:
    first = _feature_dir(tmp_path, "active", "2026-06-09-first")
    second = _feature_dir(tmp_path, "active", "2026-06-09-second")
    for feature, branch in ((first, "first"), (second, "second")):
        _write_valid_spec(feature / "spec.md", status="In Progress")
        _write_valid_plan(feature / "plan.md", status="In Progress", branch=f"codex/{branch}")
        _write_valid_tasks(
            feature / "tasks.md",
            status="In Progress",
            branch=f"codex/{branch}",
            touch_set="src/parallax/domains/macro_intel/repositories/macro_intel_repository.py",
            conflict_set="none",
        )
        _write_valid_verification(feature / "verification.md", status="In Progress", branch=f"codex/{branch}")

    issues = validate_sdd_root(tmp_path)

    assert "active-touch-conflict" in _issue_codes(issues)


def _feature_dir(root: Path, lane: str, slug: str) -> Path:
    path = root / "docs" / "sdd" / "features" / lane / slug
    path.mkdir(parents=True)
    return path


def _write_valid_spec(path: Path, *, status: str) -> None:
    path.write_text(
        "\n".join(
            [
                "# Spec - Valid",
                "",
                f"**Status**: {status}",
                "**Date**: 2026-06-09",
                "**Owner**: Codex",
                "**Approved by**: qinghuan",
                "**Approved at**: 2026-06-09",
                "",
                "## Clarifications",
                "",
                "| Question | Answer | Approved by | Approved at |",
                "|----------|--------|-------------|-------------|",
                "| Scope? | Harness only. | qinghuan | 2026-06-09 |",
                "",
                "## Requirement Checklist",
                "",
                "| Requirement | Quality gate |",
                "|-------------|--------------|",
                "| Gate truth. | Validator checks it. |",
                "",
                "## Acceptance criteria",
                "",
                "- AC1. WHEN evidence exists THEN the harness SHALL validate it.",
            ]
        ),
        encoding="utf-8",
    )


def _write_valid_plan(path: Path, *, status: str, branch: str = "codex/harness") -> None:
    path.write_text(
        "\n".join(
            [
                "# Plan - Valid",
                "",
                f"**Status**: {status}",
                "**Date**: 2026-06-09",
                "**Worktree**: `.worktrees/harness`",
                f"**Branch**: `{branch}`",
                "**Approved by**: qinghuan",
                "**Approved at**: 2026-06-09",
                "",
                "## Analyze Gate",
                "",
                "| Check | Result |",
                "|-------|--------|",
                "| Spec maps to tasks. | Pass. |",
                "",
                "## Acceptance test commands",
                "",
                "- AC1: `uv run pytest tests/architecture/test_sdd_artifact_validator.py`",
            ]
        ),
        encoding="utf-8",
    )


def _write_valid_tasks(
    path: Path,
    *,
    status: str,
    branch: str = "codex/harness",
    touch_set: str = "scripts/validate_sdd_artifacts.py",
    conflict_set: str = "scripts/regen_sdd_work_index.py",
) -> None:
    path.write_text(
        "\n".join(
            [
                "# Tasks - Valid",
                "",
                f"**Status**: {status}",
                "**Owning plan**: `docs/sdd/features/active/2026-06-09-valid/plan.md`",
                "**Worktree**: `.worktrees/harness`",
                f"**Branch**: `{branch}`",
                "**Approved by**: qinghuan",
                "**Approved at**: 2026-06-09",
                "",
                "## Gate Compliance",
                "",
                "| Gate | Evidence |",
                "|------|----------|",
                "| Clarify | `spec.md` includes `## Clarifications`. |",
                "| Checklist | `spec.md` includes `## Requirement Checklist`. |",
                "| Analyze | `plan.md` includes `## Analyze Gate`. |",
                "",
                "## Tasks",
                "",
                "### Task 1 - Valid",
                "",
                "- **File(s)**: `tests/architecture/test_sdd_artifact_validator.py`, "
                "`scripts/validate_sdd_artifacts.py`",
                "- **Owner**: parent",
                "- **Depends on**: none",
                f"- **Touch set**: `{touch_set}`",
                f"- **Conflict set**: `{conflict_set}`",
                "- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::"
                "test_verified_feature_requires_successful_make_check_all_evidence` - "
                "asserts false Verified records fail.",
                "- **Subagent handoff**: not delegated",
                "- **Implementation**: Create validator.",
                "- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py -q`",
                "- **Review owner**: parent",
                "- **Status**: [x]",
            ]
        ),
        encoding="utf-8",
    )


def _write_valid_verification(path: Path, *, status: str, branch: str = "codex/harness") -> None:
    path.write_text(
        "\n".join(
            [
                "# Verification - Valid",
                "",
                f"**Status**: {status}",
                "**Date**: 2026-06-09",
                "**Owning spec**: `docs/sdd/features/completed/2026-06-09-valid/spec.md`",
                "**Owning plan**: `docs/sdd/features/completed/2026-06-09-valid/plan.md`",
                f"**Branch**: `{branch}`",
                "**Worktree**: `.worktrees/harness`",
                "**Approved by**: qinghuan",
                "**Approved at**: 2026-06-09",
                "",
                "## Spec compliance",
                "",
                "| Acceptance criterion | Status | Evidence |",
                "|----------------------|--------|----------|",
                "| AC1 | Pass | `make check-all` exited 0. |",
                "",
                "## Verification commands",
                "",
                "```text",
                "$ make check-all",
                "all checks passed",
                "exit code: 0",
                "```",
                "",
                "## Coverage",
                "",
                "| metric | value | threshold | status |",
                "|--------|-------|-----------|--------|",
                "| line | 91% | >= 80% | Pass |",
                "",
                "## Skipped tests",
                "",
                "Number of skipped tests in the run above: 0",
                "",
                "## E2E golden path",
                "",
                "- [x] /readyz returned 200",
                "- [x] writer wrote a row visible to a separate process",
                "- [x] /api/recent returned the injected event",
                "- [x] WS /ws/live pushed within 5s",
                "- [x] testcontainers PG and uvicorn subprocess cleaned up",
            ]
        ),
        encoding="utf-8",
    )


def _issue_codes(issues: object) -> set[str]:
    return {issue.code for issue in issues}
