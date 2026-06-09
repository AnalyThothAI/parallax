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


def test_feature_rejects_mixed_artifact_statuses(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "completed", "2026-06-09-mixed-status")
    _write_valid_spec(feature / "spec.md", status="Verified")
    _write_valid_plan(feature / "plan.md", status="Verified")
    _write_valid_tasks(feature / "tasks.md", status="Verified")
    _write_valid_verification(feature / "verification.md", status="Superseded")
    for artifact_name in ("spec.md", "plan.md", "tasks.md", "verification.md"):
        _append_successor_reference(feature / artifact_name)

    issues = validate_sdd_root(tmp_path)

    assert "artifact-status-mismatch" in _issue_codes(issues)


def test_feature_rejects_unexpected_artifact_files(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-extra-artifact")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _write_valid_plan(feature / "plan.md", status="In Progress")
    _write_valid_tasks(feature / "tasks.md", status="In Progress", task_status="[~]")
    _write_valid_verification(feature / "verification.md", status="In Progress")
    (feature / "notes.md").write_text("old planning notes\n", encoding="utf-8")

    issues = validate_sdd_root(tmp_path)

    assert "unexpected-artifact" in _issue_codes(issues)


def test_artifact_owning_links_must_point_to_same_feature(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-cross-linked-feature")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _write_valid_plan(feature / "plan.md", status="In Progress")
    _write_valid_tasks(feature / "tasks.md", status="In Progress", task_status="[~]")
    _write_valid_verification(feature / "verification.md", status="In Progress")
    _replace_metadata_link(feature / "plan.md", "Owning spec", "docs/sdd/features/active/2026-06-09-other/spec.md")
    _replace_metadata_link(feature / "tasks.md", "Owning plan", "docs/sdd/features/active/2026-06-09-other/plan.md")
    _replace_metadata_link(
        feature / "verification.md",
        "Owning spec",
        "docs/sdd/features/active/2026-06-09-other/spec.md",
    )
    _replace_metadata_link(
        feature / "verification.md",
        "Owning plan",
        "docs/sdd/features/active/2026-06-09-other/plan.md",
    )

    issues = validate_sdd_root(tmp_path)

    assert "artifact-owning-link-mismatch" in _issue_codes(issues)
    assert sum(issue.code == "artifact-owning-link-mismatch" for issue in issues) == 4


def test_plan_acceptance_commands_must_cover_spec_acceptance_criteria(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-missing-ac-command")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _append_acceptance_criterion(feature / "spec.md", 2)
    _write_valid_plan(feature / "plan.md", status="In Progress")
    _append_acceptance_command(feature / "plan.md", 3)
    _write_valid_tasks(feature / "tasks.md", status="In Progress", task_status="[~]")
    _write_valid_verification(feature / "verification.md", status="In Progress")

    issues = validate_sdd_root(tmp_path)

    assert "acceptance-command-mismatch" in _issue_codes(issues)
    assert any(
        "missing commands for AC2; commands without spec criteria for AC3" in issue.message for issue in issues
    )


def test_acceptance_criteria_and_commands_require_contiguous_numbers(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-ac-number-gap")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _append_acceptance_criterion(feature / "spec.md", 3)
    _write_valid_plan(feature / "plan.md", status="In Progress")
    _append_acceptance_command(feature / "plan.md", 3)
    _write_valid_tasks(feature / "tasks.md", status="In Progress", task_status="[~]")
    _write_valid_verification(feature / "verification.md", status="In Progress")

    issues = validate_sdd_root(tmp_path)

    assert "acceptance-numbering-invalid" in _issue_codes(issues)
    assert sum(issue.code == "acceptance-numbering-invalid" for issue in issues) == 2


def test_plan_acceptance_commands_must_be_command_shaped(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-prose-ac-command")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _write_valid_plan(feature / "plan.md", status="In Progress")
    _replace_acceptance_command(feature / "plan.md", 1, "read the docs")
    _write_valid_tasks(feature / "tasks.md", status="In Progress", task_status="[~]")
    _write_valid_verification(feature / "verification.md", status="In Progress")

    issues = validate_sdd_root(tmp_path)

    assert "acceptance-command-invalid" in _issue_codes(issues)


def test_superseded_feature_requires_machine_readable_successor(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "completed", "2026-06-09-prose-successor")
    _write_valid_spec(feature / "spec.md", status="Superseded")
    _write_valid_plan(feature / "plan.md", status="Superseded")
    _write_valid_tasks(feature / "tasks.md", status="Superseded")
    _write_valid_verification(feature / "verification.md", status="Superseded")
    for artifact_name in ("spec.md", "plan.md", "tasks.md", "verification.md"):
        _append_prose_successor_reference(feature / artifact_name)

    issues = validate_sdd_root(tmp_path)

    assert "superseded-missing-successor" in _issue_codes(issues)


def test_superseded_feature_requires_approval_metadata(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "completed", "2026-06-09-superseded-without-approval")
    successor = _feature_dir(tmp_path, "active", "2026-06-09-successor")
    _write_valid_spec(successor / "spec.md", status="In Progress")
    _write_valid_plan(successor / "plan.md", status="In Progress")
    _write_valid_tasks(successor / "tasks.md", status="In Progress", task_status="[~]")
    _write_valid_verification(successor / "verification.md", status="In Progress")
    _write_valid_spec(feature / "spec.md", status="Superseded")
    _write_valid_plan(feature / "plan.md", status="Superseded")
    _write_valid_tasks(feature / "tasks.md", status="Superseded")
    _write_valid_verification(feature / "verification.md", status="Superseded")
    for artifact_name in ("spec.md", "plan.md", "tasks.md", "verification.md"):
        _append_machine_successor_reference(feature / artifact_name)
        _remove_approval_metadata(feature / artifact_name)

    issues = validate_sdd_root(tmp_path)

    assert "missing-approval-metadata" in _issue_codes(issues)


def test_superseded_feature_requires_structured_tasks(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "completed", "2026-06-09-superseded-unstructured-tasks")
    successor = _feature_dir(tmp_path, "active", "2026-06-09-successor")
    _write_valid_spec(successor / "spec.md", status="In Progress")
    _write_valid_plan(successor / "plan.md", status="In Progress")
    _write_valid_tasks(successor / "tasks.md", status="In Progress", task_status="[~]")
    _write_valid_verification(successor / "verification.md", status="In Progress")
    _write_valid_spec(feature / "spec.md", status="Superseded")
    _write_valid_plan(feature / "plan.md", status="Superseded")
    _write_unstructured_superseded_tasks(feature / "tasks.md")
    _write_valid_verification(feature / "verification.md", status="Superseded")
    for artifact_name in ("spec.md", "plan.md", "tasks.md", "verification.md"):
        _append_machine_successor_reference(feature / artifact_name)

    issues = validate_sdd_root(tmp_path)

    assert "task-missing-coordination-fields" in _issue_codes(issues)


def test_superseded_feature_requires_one_successor(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "completed", "2026-06-09-superseded-split-successor")
    successor_a = _feature_dir(tmp_path, "active", "2026-06-09-successor-a")
    successor_b = _feature_dir(tmp_path, "active", "2026-06-09-successor-b")
    for successor, touch_set in (
        (successor_a, "scripts/validate_sdd_artifacts.py"),
        (successor_b, "tests/architecture/test_sdd_artifact_validator.py"),
    ):
        _write_valid_spec(successor / "spec.md", status="In Progress")
        _write_valid_plan(successor / "plan.md", status="In Progress")
        _write_valid_tasks(successor / "tasks.md", status="In Progress", touch_set=touch_set, task_status="[~]")
        _write_valid_verification(successor / "verification.md", status="In Progress")

    _write_valid_spec(feature / "spec.md", status="Superseded")
    _write_valid_plan(feature / "plan.md", status="Superseded")
    _write_valid_tasks(feature / "tasks.md", status="Superseded")
    _write_valid_verification(feature / "verification.md", status="Superseded")
    _insert_successor_reference(feature / "spec.md", "2026-06-09-successor-a")
    for artifact_name in ("plan.md", "tasks.md", "verification.md"):
        _insert_successor_reference(feature / artifact_name, "2026-06-09-successor-b")

    issues = validate_sdd_root(tmp_path)

    assert "superseded-successor-mismatch" in _issue_codes(issues)


def test_verified_feature_ignores_old_success_outside_verification_commands(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "completed", "2026-06-09-old-success")
    _write_valid_spec(feature / "spec.md", status="Verified")
    _write_valid_plan(feature / "plan.md", status="Verified")
    _write_valid_tasks(feature / "tasks.md", status="Verified")
    _write_valid_verification(
        feature / "verification.md",
        status="Verified",
        verification_command_lines=(
            "$ make check-all",
            "integration failed after unit checks",
            "exit code: 2",
        ),
        other_command_lines=(
            "$ make check-all",
            "old run passed before this change",
            "exit code: 0",
        ),
    )

    issues = validate_sdd_root(tmp_path)

    assert "verified-missing-check-all" in _issue_codes(issues)
    assert "verified-contradicts-evidence" in _issue_codes(issues)


def test_verified_feature_requires_skipped_table_to_match_skip_count(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "completed", "2026-06-09-bad-skips")
    _write_valid_spec(feature / "spec.md", status="Verified")
    _write_valid_plan(feature / "plan.md", status="Verified")
    _write_valid_tasks(feature / "tasks.md", status="Verified")
    _write_valid_verification(
        feature / "verification.md",
        status="Verified",
        skipped_count="1",
        skipped_table_rows=(
            "| count | reason | acceptable? |",
            "|-------|--------|-------------|",
            "| 1 | unknown skip | No |",
        ),
    )

    issues = validate_sdd_root(tmp_path)

    assert "verified-unexplained-skips" in _issue_codes(issues)


def test_complete_tasks_require_matching_verification_evidence(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-complete-task-without-evidence")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _write_valid_plan(feature / "plan.md", status="In Progress")
    _write_valid_tasks(
        feature / "tasks.md",
        status="In Progress",
        verification="uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_expected_gate -q",
        task_status="[x]",
    )
    _write_valid_verification(
        feature / "verification.md",
        status="In Progress",
        verification_command_lines=(
            "$ make check-all",
            "not final evidence",
            "exit code: 2",
        ),
        other_command_lines=(
            "$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_other_gate -q",
            "1 passed in 0.01s",
            "exit code: 0",
        ),
    )

    issues = validate_sdd_root(tmp_path)

    assert "task-complete-missing-verification-evidence" in _issue_codes(issues)


def test_complete_task_evidence_ignores_commands_outside_evidence_sections(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-complete-task-notes-evidence")
    expected_command = "uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_expected_gate -q"
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _write_valid_plan(feature / "plan.md", status="In Progress")
    _write_valid_tasks(
        feature / "tasks.md",
        status="In Progress",
        verification=expected_command,
        task_status="[x]",
    )
    _write_valid_verification(
        feature / "verification.md",
        status="In Progress",
        other_command_lines=(
            "$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_other_gate -q",
            "1 passed in 0.01s",
            "exit code: 0",
        ),
    )
    _append_notes_command_evidence(feature / "verification.md", expected_command)

    issues = validate_sdd_root(tmp_path)

    assert "task-complete-missing-verification-evidence" in _issue_codes(issues)


def test_complete_tasks_require_review_result_evidence(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-complete-task-without-review")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _write_valid_plan(feature / "plan.md", status="In Progress")
    _write_valid_tasks(
        feature / "tasks.md",
        status="In Progress",
        review_result="not delegated",
        task_status="[x]",
    )
    _write_valid_verification(feature / "verification.md", status="In Progress")

    issues = validate_sdd_root(tmp_path)

    assert "task-complete-missing-review-evidence" in _issue_codes(issues)


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
    assert "task-missing-agent-loop-fields" in _issue_codes(issues)


def test_tasks_reject_invalid_coordination_field_values(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-invalid-task-values")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _write_valid_plan(feature / "plan.md", status="In Progress")
    _write_valid_tasks(
        feature / "tasks.md",
        status="In Progress",
        touch_set="none",
        failing_test_first="none",
        verification="done manually",
        task_status="[maybe]",
    )
    _write_valid_verification(feature / "verification.md", status="In Progress")

    issues = validate_sdd_root(tmp_path)

    invalid_issues = [issue for issue in issues if issue.code == "task-invalid-coordination-fields"]
    assert invalid_issues
    invalid_text = " ".join(issue.message for issue in invalid_issues)
    assert "touch set" in invalid_text
    assert "failing test first" in invalid_text
    assert "verification" in invalid_text
    assert "status" in invalid_text


def test_tasks_allow_explicit_none_dependency_and_not_delegated_handoff(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-valid-none-values")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _write_valid_plan(feature / "plan.md", status="In Progress")
    _write_valid_tasks(
        feature / "tasks.md",
        status="In Progress",
        depends_on="none",
        subagent_handoff="not delegated",
        task_status="[~]",
    )
    _write_valid_verification(feature / "verification.md", status="In Progress")

    issues = validate_sdd_root(tmp_path)

    assert "task-invalid-coordination-fields" not in _issue_codes(issues)


def test_non_delegated_handoff_rejects_prose_suffix(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-prose-handoff")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _write_valid_plan(feature / "plan.md", status="In Progress")
    _write_valid_tasks(
        feature / "tasks.md",
        status="In Progress",
        subagent_handoff="not delegated; parent handled the context inline",
        subagent_report="not delegated",
        review_result="parent-reviewed",
        task_status="[~]",
    )
    _write_valid_verification(feature / "verification.md", status="In Progress")

    issues = validate_sdd_root(tmp_path)

    invalid_issues = [issue for issue in issues if issue.code == "task-invalid-review-fields"]
    assert invalid_issues
    assert "subagent handoff" in " ".join(issue.message for issue in invalid_issues)


def test_delegated_tasks_require_review_evidence_fields(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-delegated-review-evidence")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _write_valid_plan(feature / "plan.md", status="In Progress")
    _write_valid_tasks(
        feature / "tasks.md",
        status="In Progress",
        subagent_handoff="docs/agent-playbook/subagent-handoff-template.md",
        subagent_report="",
        review_result="",
        task_status="[~]",
    )
    _write_valid_verification(feature / "verification.md", status="In Progress")

    issues = validate_sdd_root(tmp_path)

    assert "task-missing-review-fields" in _issue_codes(issues)


def test_delegated_tasks_reject_invalid_review_evidence_values(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-invalid-review-evidence")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _write_valid_plan(feature / "plan.md", status="In Progress")
    _write_valid_tasks(
        feature / "tasks.md",
        status="In Progress",
        subagent_handoff="docs/agent-playbook/subagent-handoff-template.md",
        subagent_report="looks good",
        review_result="maybe",
        task_status="[~]",
    )
    _write_valid_verification(feature / "verification.md", status="In Progress")

    issues = validate_sdd_root(tmp_path)

    assert "task-invalid-review-fields" in _issue_codes(issues)


def test_delegated_tasks_require_report_artifact(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-missing-subagent-report")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _write_valid_plan(feature / "plan.md", status="In Progress")
    _write_valid_tasks(
        feature / "tasks.md",
        status="In Progress",
        subagent_handoff="docs/agent-playbook/subagent-handoff-template.md",
        subagent_report="docs/generated/subagent-reports/missing.md",
        review_result="accepted",
        task_status="[~]",
    )
    _write_valid_verification(feature / "verification.md", status="In Progress")

    issues = validate_sdd_root(tmp_path)

    assert "task-missing-subagent-report-artifact" in _issue_codes(issues)


def test_delegated_tasks_require_handoff_artifact(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-missing-subagent-handoff")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _write_valid_plan(feature / "plan.md", status="In Progress")
    report = tmp_path / "docs" / "generated" / "subagent-reports" / "valid.md"
    _write_valid_subagent_report(report)
    _write_valid_tasks(
        feature / "tasks.md",
        status="In Progress",
        subagent_handoff="docs/generated/subagent-handoffs/missing.md",
        subagent_report="docs/generated/subagent-reports/valid.md",
        review_result="accepted",
        task_status="[~]",
    )
    _write_valid_verification(feature / "verification.md", status="In Progress")

    issues = validate_sdd_root(tmp_path)

    assert "task-missing-subagent-handoff-artifact" in _issue_codes(issues)


def test_delegated_tasks_validate_report_artifact_against_task(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-invalid-subagent-report")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _write_valid_plan(feature / "plan.md", status="In Progress")
    report = tmp_path / "docs" / "generated" / "subagent-reports" / "invalid.md"
    report.parent.mkdir(parents=True)
    report.write_text(
        "\n".join(
            [
                "# Subagent Report",
                "",
                "Mode: write-allowed",
                "",
                "## Findings",
                "- Wrote outside scope.",
                "",
                "## Scope Adherence",
                "- Owned scope: pass",
                "- Conflict set: pass",
                "",
                "## Changed Files",
                "- `scripts/dispatch_sdd_task.py`",
                "",
                "## Verification Evidence",
                "```text",
                "$ uv run pytest tests/architecture/test_agent_playbook_contracts.py -q",
                "failed",
                "exit code: 1",
                "```",
                "",
                "## Remaining Risks",
                "- needs repair",
            ]
        ),
        encoding="utf-8",
    )
    _write_valid_tasks(
        feature / "tasks.md",
        status="In Progress",
        subagent_handoff="docs/agent-playbook/subagent-handoff-template.md",
        subagent_report="docs/generated/subagent-reports/invalid.md",
        review_result="needs-repair",
        task_status="[~]",
    )
    _write_valid_verification(feature / "verification.md", status="In Progress")

    issues = validate_sdd_root(tmp_path)

    assert "task-invalid-subagent-report-artifact" in _issue_codes(issues)


def test_tasks_reject_unresolved_dependencies(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-unresolved-dependency")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _write_valid_plan(feature / "plan.md", status="In Progress")
    _write_valid_tasks(
        feature / "tasks.md",
        status="In Progress",
        depends_on="Task 99",
    )
    _write_valid_verification(feature / "verification.md", status="In Progress")

    issues = validate_sdd_root(tmp_path)

    assert "task-invalid-dependencies" in _issue_codes(issues)


def test_tasks_require_unique_contiguous_numbers(tmp_path: Path) -> None:
    duplicate_feature = _feature_dir(tmp_path, "active", "2026-06-09-duplicate-task-number")
    _write_valid_spec(duplicate_feature / "spec.md", status="In Progress")
    _write_valid_plan(duplicate_feature / "plan.md", status="In Progress")
    _write_valid_tasks(
        duplicate_feature / "tasks.md",
        status="In Progress",
        conflict_set="coordinate with 2026-06-09-task-number-gap for numbering fixture.",
    )
    _append_valid_task(duplicate_feature / "tasks.md", task_number=1, depends_on="none", task_status="[x]")
    _write_valid_verification(duplicate_feature / "verification.md", status="In Progress")

    gap_feature = _feature_dir(tmp_path, "active", "2026-06-09-task-number-gap")
    _write_valid_spec(gap_feature / "spec.md", status="In Progress")
    _write_valid_plan(gap_feature / "plan.md", status="In Progress", branch="codex/task-number-gap")
    _write_valid_tasks(
        gap_feature / "tasks.md",
        status="In Progress",
        branch="codex/task-number-gap",
        touch_set="tests/architecture/test_agent_playbook_contracts.py",
        conflict_set="coordinate with 2026-06-09-duplicate-task-number for numbering fixture.",
        task_status="[~]",
    )
    _append_valid_task(gap_feature / "tasks.md", task_number=3, depends_on="Task 1", task_status="[~]")
    _write_valid_verification(gap_feature / "verification.md", status="In Progress", branch="codex/task-number-gap")

    issues = validate_sdd_root(tmp_path)

    assert "task-invalid-numbering" in _issue_codes(issues)
    assert sum(issue.code == "task-invalid-numbering" for issue in issues) == 2


def test_completed_tasks_reject_incomplete_dependencies(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-complete-before-dependency")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _write_valid_plan(feature / "plan.md", status="In Progress")
    _write_valid_tasks(feature / "tasks.md", status="In Progress", task_status="[~]")
    _append_valid_task(feature / "tasks.md", task_number=2, depends_on="Task 1", task_status="[x]")
    _write_valid_verification(feature / "verification.md", status="In Progress")

    issues = validate_sdd_root(tmp_path)

    assert "task-invalid-dependencies" in _issue_codes(issues)


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


def _feature_relative_dir(path: Path) -> str:
    marker = "/docs/sdd/features/"
    feature_dir = path.parent.as_posix()
    if marker not in feature_dir:
        raise AssertionError(f"test artifact is outside SDD features: {path}")
    return "docs/sdd/features/" + feature_dir.split(marker, 1)[1]


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
    feature_dir = _feature_relative_dir(path)
    path.write_text(
        "\n".join(
            [
                "# Plan - Valid",
                "",
                f"**Status**: {status}",
                "**Date**: 2026-06-09",
                f"**Owning spec**: `{feature_dir}/spec.md`",
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
    depends_on: str = "none",
    touch_set: str = "scripts/validate_sdd_artifacts.py",
    conflict_set: str = "scripts/regen_sdd_work_index.py",
    failing_test_first: str = (
        "tests/architecture/test_sdd_artifact_validator.py::"
        "test_verified_feature_requires_successful_make_check_all_evidence"
    ),
    subagent_handoff: str = "not delegated",
    subagent_report: str = "not delegated",
    review_result: str = "parent-reviewed",
    verification: str = "uv run pytest tests/architecture/test_sdd_artifact_validator.py -q",
    task_status: str = "[x]",
) -> None:
    feature_dir = _feature_relative_dir(path)
    path.write_text(
        "\n".join(
            [
                "# Tasks - Valid",
                "",
                f"**Status**: {status}",
                f"**Owning plan**: `{feature_dir}/plan.md`",
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
                f"- **Depends on**: {depends_on}",
                f"- **Touch set**: `{touch_set}`",
                f"- **Conflict set**: `{conflict_set}`",
                f"- **Failing test first**: `{failing_test_first}` - asserts false Verified records fail.",
                f"- **Subagent handoff**: {subagent_handoff}",
                f"- **Subagent report**: {subagent_report}",
                f"- **Review result**: {review_result}",
                "- **Implementation**: Create validator.",
                f"- **Verification**: `{verification}`",
                "- **Review owner**: parent",
                "- **Factory lane**: Harness",
                "- **Deterministic constraints**: SDD validator, generated index, make check-all.",
                "- **On-demand context**: `docs/WORKFLOW.md`, `docs/sdd/_templates/`.",
                "- **Kill/defer criteria**: Stop if validator cannot prove artifact truth.",
                "- **Eval/repair signal**: Record harness failures and review defects.",
                f"- **Status**: {task_status}",
            ]
        ),
        encoding="utf-8",
    )


def _write_unstructured_superseded_tasks(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "# Tasks - Legacy",
                "",
                "**Status**: Superseded",
                "**Owning plan**: `docs/sdd/features/completed/2026-06-09-legacy/plan.md`",
                "**Worktree**: `.worktrees/legacy`",
                "**Branch**: `codex/legacy`",
                "**Approved by**: qinghuan",
                "**Approved at**: 2026-06-09",
                "",
                "## Tasks",
                "",
                "- [x] legacy checklist item",
            ]
        ),
        encoding="utf-8",
    )


def _append_valid_task(path: Path, *, task_number: int, depends_on: str, task_status: str) -> None:
    path.write_text(
        path.read_text(encoding="utf-8")
        + "\n\n"
        + "\n".join(
            [
                f"### Task {task_number} - Dependent",
                "",
                "- **File(s)**: `tests/architecture/test_sdd_artifact_validator.py`, "
                "`scripts/validate_sdd_artifacts.py`",
                "- **Owner**: parent",
                f"- **Depends on**: {depends_on}",
                "- **Touch set**: `scripts/validate_sdd_artifacts.py`",
                "- **Conflict set**: `scripts/regen_sdd_work_index.py`",
                "- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::"
                "test_completed_tasks_reject_incomplete_dependencies` - asserts completion order.",
                "- **Subagent handoff**: not delegated",
                "- **Subagent report**: not delegated",
                "- **Review result**: parent-reviewed",
                "- **Implementation**: Validate dependency completion.",
                "- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py -q`",
                "- **Review owner**: parent",
                "- **Factory lane**: Harness",
                "- **Deterministic constraints**: Complete tasks cannot depend on incomplete tasks.",
                "- **On-demand context**: `docs/sdd/README.md`, `scripts/validate_sdd_artifacts.py`.",
                "- **Kill/defer criteria**: Stop if completion order cannot be proven.",
                "- **Eval/repair signal**: `task-invalid-dependencies`.",
                f"- **Status**: {task_status}",
            ]
        ),
        encoding="utf-8",
    )


def _write_valid_verification(
    path: Path,
    *,
    status: str,
    branch: str = "codex/harness",
    verification_command_lines: tuple[str, ...] = (
        "$ make check-all",
        "all checks passed",
        "exit code: 0",
    ),
    other_command_lines: tuple[str, ...] = (
        "$ uv run pytest tests/architecture/test_sdd_artifact_validator.py -q",
        "1 passed in 0.01s",
        "exit code: 0",
    ),
    skipped_count: str = "0",
    skipped_table_rows: tuple[str, ...] = (),
) -> None:
    feature_dir = _feature_relative_dir(path)
    path.write_text(
        "\n".join(
            [
                "# Verification - Valid",
                "",
                f"**Status**: {status}",
                "**Date**: 2026-06-09",
                f"**Owning spec**: `{feature_dir}/spec.md`",
                f"**Owning plan**: `{feature_dir}/plan.md`",
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
                *verification_command_lines,
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
                f"Number of skipped tests in the run above: {skipped_count}",
                "",
                *skipped_table_rows,
                "",
                "## E2E golden path",
                "",
                "- [x] /readyz returned 200",
                "- [x] writer wrote a row visible to a separate process",
                "- [x] /api/recent returned the injected event",
                "- [x] WS /ws/live pushed within 5s",
                "- [x] testcontainers PG and uvicorn subprocess cleaned up",
                "",
                "## Other commands run",
                "",
                "```text",
                *other_command_lines,
                "```",
            ]
        ),
        encoding="utf-8",
    )


def _write_valid_subagent_report(path: Path) -> None:
    path.parent.mkdir(parents=True)
    path.write_text(
        "\n".join(
            [
                "# Subagent Report",
                "",
                "Mode: write-allowed",
                "",
                "## Findings",
                "- Task-bound report evidence.",
                "",
                "## Scope Adherence",
                "- Owned scope: pass",
                "- Conflict set: pass",
                "",
                "## Changed Files",
                "- `scripts/validate_sdd_artifacts.py`",
                "",
                "## Verification Evidence",
                "```text",
                "$ uv run pytest tests/architecture/test_sdd_artifact_validator.py -q",
                "passed",
                "exit code: 0",
                "```",
                "",
                "## Remaining Risks",
                "- none",
            ]
        ),
        encoding="utf-8",
    )


def _append_successor_reference(path: Path) -> None:
    path.write_text(
        path.read_text(encoding="utf-8")
        + "\n\nSuperseded by: `docs/sdd/features/active/2026-06-09-successor/spec.md`\n",
        encoding="utf-8",
    )


def _replace_metadata_link(path: Path, field_name: str, value: str) -> None:
    needle = f"**{field_name}**:"
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(needle):
            lines.append(f"**{field_name}**: `{value}`")
        else:
            lines.append(line)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _append_acceptance_criterion(path: Path, number: int) -> None:
    path.write_text(
        path.read_text(encoding="utf-8")
        + f"\n- AC{number}. WHEN another behavior exists THEN the harness SHALL map it to a command.\n",
        encoding="utf-8",
    )


def _append_acceptance_command(path: Path, number: int) -> None:
    path.write_text(
        path.read_text(encoding="utf-8")
        + f"\n- AC{number}: `uv run pytest tests/architecture/test_sdd_artifact_validator.py -q`\n",
        encoding="utf-8",
    )


def _replace_acceptance_command(path: Path, number: int, command: str) -> None:
    target = f"- AC{number}:"
    lines = []
    replaced = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(target):
            lines.append(f"- AC{number}: `{command}`")
            replaced = True
        else:
            lines.append(line)
    if not replaced:
        raise AssertionError(f"missing AC{number} command in {path}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _append_machine_successor_reference(path: Path) -> None:
    path.write_text(
        path.read_text(encoding="utf-8")
        + "\n\n**Superseded by**: `docs/sdd/features/active/2026-06-09-successor/`\n",
        encoding="utf-8",
    )


def _insert_successor_reference(path: Path, successor_slug: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        if line.startswith("**Status**:"):
            lines.insert(index + 1, f"**Superseded by**: `docs/sdd/features/active/{successor_slug}/`")
            break
    else:
        lines.insert(0, f"**Superseded by**: `docs/sdd/features/active/{successor_slug}/`")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _append_prose_successor_reference(path: Path) -> None:
    path.write_text(
        path.read_text(encoding="utf-8")
        + "\n\nThis record was superseded by the current active harness feature.\n",
        encoding="utf-8",
    )


def _remove_approval_metadata(path: Path) -> None:
    lines = [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if not line.startswith("**Approved by**:") and not line.startswith("**Approved at**:")
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _append_notes_command_evidence(path: Path, command: str) -> None:
    path.write_text(
        path.read_text(encoding="utf-8")
        + "\n\n## Notes\n\n```text\n"
        + f"$ {command}\n"
        + "1 passed in 0.01s\n"
        + "exit code: 0\n"
        + "```\n",
        encoding="utf-8",
    )


def _issue_codes(issues: object) -> set[str]:
    return {issue.code for issue in issues}
