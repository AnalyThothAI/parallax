from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

from scripts.agent_mode_constraints import mode_constraint_lines
from scripts.validate_sdd_artifacts import KNOWN_ISSUE_CODES, main, validate_sdd_root

ROOT = Path(__file__).resolve().parents[2]


def test_validator_issue_codes_are_registered_for_generated_lifecycle_index() -> None:
    source = ROOT / "scripts" / "validate_sdd_artifacts.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    emitted_codes = {
        node.args[0].value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "_issue"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and isinstance(node.args[0].value, str)
    }

    assert emitted_codes <= set(KNOWN_ISSUE_CODES)


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


def test_verified_feature_rejects_extra_verification_command(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "completed", "2026-06-09-extra-final-command")
    _write_valid_spec(feature / "spec.md", status="Verified")
    _write_valid_plan(feature / "plan.md", status="Verified")
    _write_valid_tasks(feature / "tasks.md", status="Verified")
    _write_valid_verification(
        feature / "verification.md",
        status="Verified",
        verification_command_lines=(
            "$ make check-all",
            "all checks passed",
            "exit code: 0",
            "$ uv run pytest tests/architecture/test_sdd_artifact_validator.py -q",
            "1 passed in 0.01s",
            "exit code: 0",
        ),
    )

    issues = validate_sdd_root(tmp_path)

    assert "verified-extra-verification-command" in _issue_codes(issues)
    assert "uv run pytest" in "\n".join(issue.message for issue in issues)


def test_verified_feature_rejects_unfenced_extra_verification_command(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "completed", "2026-06-09-unfenced-extra-final-command")
    _write_valid_spec(feature / "spec.md", status="Verified")
    _write_valid_plan(feature / "plan.md", status="Verified")
    _write_valid_tasks(feature / "tasks.md", status="Verified")
    _write_valid_verification(feature / "verification.md", status="Verified")
    verification_path = feature / "verification.md"
    verification_path.write_text(
        verification_path.read_text(encoding="utf-8").replace(
            "## Coverage",
            "$ uv run pytest tests/architecture/test_sdd_artifact_validator.py -q\n\n## Coverage",
        ),
        encoding="utf-8",
    )

    issues = validate_sdd_root(tmp_path)

    assert "verified-extra-verification-command" in _issue_codes(issues)
    assert "uv run pytest" in "\n".join(issue.message for issue in issues)


def test_verified_feature_rejects_duplicate_unfenced_make_check_all(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "completed", "2026-06-09-duplicate-final-check-all")
    _write_valid_spec(feature / "spec.md", status="Verified")
    _write_valid_plan(feature / "plan.md", status="Verified")
    _write_valid_tasks(feature / "tasks.md", status="Verified")
    _write_valid_verification(feature / "verification.md", status="Verified")
    verification_path = feature / "verification.md"
    verification_path.write_text(
        verification_path.read_text(encoding="utf-8").replace(
            "## Coverage",
            "$ make check-all\n\n## Coverage",
        ),
        encoding="utf-8",
    )

    issues = validate_sdd_root(tmp_path)

    assert "verified-extra-verification-command" in _issue_codes(issues)
    assert "exactly one `make check-all`" in "\n".join(issue.message for issue in issues)


def test_verified_feature_rejects_extra_verification_output_block(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "completed", "2026-06-09-extra-final-output-block")
    _write_valid_spec(feature / "spec.md", status="Verified")
    _write_valid_plan(feature / "plan.md", status="Verified")
    _write_valid_tasks(feature / "tasks.md", status="Verified")
    _write_valid_verification(feature / "verification.md", status="Verified")
    verification_path = feature / "verification.md"
    verification_path.write_text(
        verification_path.read_text(encoding="utf-8").replace(
            "## Coverage",
            "```text\n"
            "diagnostic output from a separate run\n"
            "exit code: 1\n"
            "```\n\n"
            "## Coverage",
        ),
        encoding="utf-8",
    )

    issues = validate_sdd_root(tmp_path)

    assert "verified-extra-verification-output" in _issue_codes(issues)
    assert "exactly one fenced transcript block" in "\n".join(issue.message for issue in issues)


def test_verified_feature_rejects_duplicate_verification_commands_section(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "completed", "2026-06-09-duplicate-verification-commands")
    _write_valid_spec(feature / "spec.md", status="Verified")
    _write_valid_plan(feature / "plan.md", status="Verified")
    _write_valid_tasks(feature / "tasks.md", status="Verified")
    _write_valid_verification(feature / "verification.md", status="Verified")
    verification_path = feature / "verification.md"
    verification_path.write_text(
        verification_path.read_text(encoding="utf-8").replace(
            "## Coverage",
            "## Verification commands\n\n"
            "```text\n"
            "$ make check-all\n"
            "stale failed transcript\n"
            "exit code: 1\n"
            "```\n\n"
            "## Coverage",
        ),
        encoding="utf-8",
    )

    issues = validate_sdd_root(tmp_path)

    assert "duplicate-gate-section" in _issue_codes(issues)
    assert "## Verification commands" in "\n".join(issue.message for issue in issues)


def test_verified_spec_compliance_rows_require_matching_command_evidence(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "completed", "2026-06-09-spec-compliance-without-evidence")
    missing_command = "uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_missing_gate -q"
    _write_valid_spec(feature / "spec.md", status="Verified")
    _write_valid_plan(feature / "plan.md", status="Verified")
    _write_valid_tasks(feature / "tasks.md", status="Verified")
    _write_valid_verification(feature / "verification.md", status="Verified")
    _replace_spec_compliance_row(
        feature / "verification.md",
        f"| AC1 | Pass | `{missing_command}` passed. |",
    )

    issues = validate_sdd_root(tmp_path)

    assert "verified-missing-spec-compliance-evidence" in _issue_codes(issues)


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


def test_feature_lanes_reject_loose_legacy_files(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-clean-feature")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _write_valid_plan(feature / "plan.md", status="In Progress")
    _write_valid_tasks(feature / "tasks.md", status="In Progress", task_status="[~]")
    _write_valid_verification(feature / "verification.md", status="In Progress")
    loose_file = tmp_path / "docs" / "sdd" / "features" / "active" / "legacy-note.md"
    loose_file.write_text("old planning notes\n", encoding="utf-8")

    issues = validate_sdd_root(tmp_path)

    unexpected = [issue for issue in issues if issue.code == "unexpected-artifact"]
    assert unexpected
    assert any(issue.path.endswith("features/active/legacy-note.md") for issue in unexpected)


def test_tasks_reject_final_verification_checklist_duplication(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-duplicated-final-verification")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _write_valid_plan(feature / "plan.md", status="In Progress")
    _write_valid_tasks(feature / "tasks.md", status="In Progress", task_status="[~]")
    _write_valid_verification(feature / "verification.md", status="In Progress")
    (feature / "tasks.md").write_text(
        (feature / "tasks.md").read_text(encoding="utf-8")
        + "\n\n## Final verification\n\n"
        + "- [ ] `make check-all`\n"
        + "- [ ] Paste evidence into `verification.md`.\n",
        encoding="utf-8",
    )

    issues = validate_sdd_root(tmp_path)

    assert "tasks-final-verification-duplicated" in _issue_codes(issues)


def test_feature_directory_name_and_date_metadata_are_machine_valid(tmp_path: Path) -> None:
    invalid_slug = _feature_dir(tmp_path, "active", "freeform-plan")
    _write_valid_spec(invalid_slug / "spec.md", status="In Progress")
    _write_valid_plan(invalid_slug / "plan.md", status="In Progress")
    _write_valid_tasks(invalid_slug / "tasks.md", status="In Progress", task_status="[~]")
    _write_valid_verification(invalid_slug / "verification.md", status="In Progress")

    mismatched_date = _feature_dir(tmp_path, "active", "2026-06-09-date-mismatch")
    _write_valid_spec(mismatched_date / "spec.md", status="In Progress")
    _replace_metadata_field(mismatched_date / "spec.md", "Date", "2026-06-08")
    _write_valid_plan(mismatched_date / "plan.md", status="In Progress")
    _write_valid_tasks(
        mismatched_date / "tasks.md",
        status="In Progress",
        touch_set="tests/architecture/test_agent_playbook_contracts.py",
        task_status="[~]",
    )
    _write_valid_verification(mismatched_date / "verification.md", status="In Progress")

    issues = validate_sdd_root(tmp_path)

    assert "feature-slug-invalid" in _issue_codes(issues)
    assert sum(issue.code == "feature-slug-invalid" for issue in issues) == 2


def test_artifact_metadata_dates_require_canonical_real_dates(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-non-canonical-metadata-dates")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _replace_metadata_field(feature / "spec.md", "Approved at", "20260609")
    _write_valid_plan(feature / "plan.md", status="In Progress")
    _replace_metadata_field(feature / "plan.md", "Date", "20260609")
    _write_valid_tasks(feature / "tasks.md", status="In Progress", task_status="[~]")
    _replace_metadata_field(feature / "tasks.md", "Approved at", "2026-99-99")
    _write_valid_verification(feature / "verification.md", status="In Progress")

    issues = validate_sdd_root(tmp_path)

    assert "metadata-date-invalid" in _issue_codes(issues)
    messages = "\n".join(issue.message for issue in issues if issue.code == "metadata-date-invalid")
    assert "spec.md approved at" in messages
    assert "plan.md date" in messages
    assert "tasks.md approved at" in messages


def test_worktree_branch_metadata_must_be_machine_valid(tmp_path: Path) -> None:
    template_feature = _feature_dir(tmp_path, "active", "2026-06-09-template-worktree")
    _write_valid_spec(template_feature / "spec.md", status="In Progress")
    _write_valid_plan(template_feature / "plan.md", status="In Progress")
    _replace_metadata_field(template_feature / "plan.md", "Worktree", "`.worktrees/<branch-slug>/`")
    _write_valid_tasks(template_feature / "tasks.md", status="In Progress", task_status="[~]")
    _write_valid_verification(template_feature / "verification.md", status="In Progress")

    mismatch_feature = _feature_dir(tmp_path, "active", "2026-06-09-mismatched-worktree")
    _write_valid_spec(mismatch_feature / "spec.md", status="In Progress")
    _write_valid_plan(mismatch_feature / "plan.md", status="In Progress", branch="codex/expected")
    _write_valid_tasks(
        mismatch_feature / "tasks.md",
        status="In Progress",
        branch="codex/expected",
        touch_set="tests/architecture/test_agent_playbook_contracts.py",
        task_status="[~]",
    )
    _replace_metadata_field(mismatch_feature / "tasks.md", "Worktree", "`.worktrees/other`")
    _write_valid_verification(mismatch_feature / "verification.md", status="In Progress", branch="codex/expected")

    issues = validate_sdd_root(tmp_path)

    assert "worktree-metadata-invalid" in _issue_codes(issues)
    assert sum(issue.code == "worktree-metadata-invalid" for issue in issues) == 2


def test_plan_preflight_worktree_claims_must_match_metadata(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-stale-preflight")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _write_valid_plan(feature / "plan.md", status="In Progress")
    _insert_plan_preflight_line(
        feature / "plan.md",
        "- [x] Worktree exists at `.worktrees/other` and `git branch --show-current` matches `codex/other`.",
    )
    _write_valid_tasks(feature / "tasks.md", status="In Progress", task_status="[~]")
    _write_valid_verification(feature / "verification.md", status="In Progress")

    issues = validate_sdd_root(tmp_path)

    assert "plan-preflight-metadata-mismatch" in _issue_codes(issues)


def test_spec_background_requires_source_citations(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-uncited-background")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _replace_section_body(
        feature / "spec.md",
        "## Background",
        ("The current harness has a source-backed background claim without a citation.",),
    )
    _write_valid_plan(feature / "plan.md", status="In Progress")
    _write_valid_tasks(feature / "tasks.md", status="In Progress", task_status="[~]")
    _write_valid_verification(feature / "verification.md", status="In Progress")

    issues = validate_sdd_root(tmp_path)

    assert "spec-background-uncited" in _issue_codes(issues)


def test_spec_background_rejects_stale_local_citation_lines(tmp_path: Path) -> None:
    workflow = tmp_path / "docs" / "WORKFLOW.md"
    workflow.parent.mkdir(parents=True, exist_ok=True)
    workflow.write_text(
        "\n".join(
            [
                "# Workflow",
                "",
                "Completion requires `make check-all` evidence before a completion claim.",
            ]
        ),
        encoding="utf-8",
    )
    feature = _feature_dir(tmp_path, "active", "2026-06-09-stale-background-citation")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _replace_section_body(
        feature / "spec.md",
        "## Background",
        ("Completion requires `make check-all` evidence in `docs/WORKFLOW.md:1`.",),
    )
    _write_valid_plan(feature / "plan.md", status="In Progress")
    _write_valid_tasks(feature / "tasks.md", status="In Progress", task_status="[~]")
    _write_valid_verification(feature / "verification.md", status="In Progress")

    issues = validate_sdd_root(tmp_path)

    assert "spec-background-uncited" in _issue_codes(issues)
    assert "does not mention cited evidence token" in "\n".join(issue.message for issue in issues)


def test_gate_sections_require_non_placeholder_evidence(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-empty-gates")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _replace_section_body(
        feature / "spec.md",
        "## Clarifications",
        (
            "| Question | Answer | Approved by | Approved at |",
            "|----------|--------|-------------|-------------|",
            "|          |        |             |             |",
        ),
    )
    _replace_section_body(
        feature / "spec.md",
        "## Requirement Checklist",
        (
            "| Requirement | Quality gate |",
            "|-------------|--------------|",
            "|             |              |",
        ),
    )
    _write_valid_plan(feature / "plan.md", status="In Progress")
    _replace_section_body(
        feature / "plan.md",
        "## Analyze Gate",
        (
            "| Check | Result |",
            "|-------|--------|",
            "|       |        |",
        ),
    )
    _write_valid_tasks(feature / "tasks.md", status="In Progress", task_status="[~]")
    _replace_section_body(
        feature / "tasks.md",
        "## Gate Compliance",
        (
            "| Gate | Evidence |",
            "|------|----------|",
            "|      |          |",
        ),
    )
    _write_valid_verification(feature / "verification.md", status="In Progress")

    issues = validate_sdd_root(tmp_path)

    assert "gate-evidence-missing" in _issue_codes(issues)
    assert sum(issue.code == "gate-evidence-missing" for issue in issues) == 4


def test_gate_evidence_rejects_fenced_table_rows(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-fenced-gate-tables")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _replace_section_body(
        feature / "spec.md",
        "## Clarifications",
        (
            "```md",
            "| Question | Answer | Approved by | Approved at |",
            "|----------|--------|-------------|-------------|",
            "| Is this real evidence? | No, it is an example. | qinghuan | 2026-06-09 |",
            "```",
        ),
    )
    _replace_section_body(
        feature / "spec.md",
        "## Requirement Checklist",
        (
            "```md",
            "| Requirement | Quality gate |",
            "|-------------|--------------|",
            "| Fenced tables must not count. | Validator rejects examples. |",
            "```",
        ),
    )
    _write_valid_plan(feature / "plan.md", status="In Progress")
    _replace_section_body(
        feature / "plan.md",
        "## Analyze Gate",
        (
            "```md",
            "| Check | Result |",
            "|-------|--------|",
            "| Evidence scope | Pass: fenced examples are not evidence. |",
            "```",
        ),
    )
    _write_valid_tasks(feature / "tasks.md", status="In Progress", task_status="[~]")
    _replace_section_body(
        feature / "tasks.md",
        "## Gate Compliance",
        (
            "```md",
            "| Gate | Evidence |",
            "|------|----------|",
            "| Clarify | `spec.md` includes `## Clarifications`. |",
            "| Checklist | `spec.md` includes `## Requirement Checklist`. |",
            "| Analyze | `plan.md` includes `## Analyze Gate`. |",
            "| Implement | Tasks below are TDD ordered. |",
            "| Verify | `verification.md` captures command output. |",
            "```",
        ),
    )
    _write_valid_verification(feature / "verification.md", status="In Progress")

    issues = validate_sdd_root(tmp_path)

    assert "gate-evidence-missing" in _issue_codes(issues)
    assert sum(issue.code == "gate-evidence-missing" for issue in issues) == 4


def test_verified_feature_rejects_fenced_spec_compliance_and_coverage_tables(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "completed", "2026-06-09-fenced-final-tables")
    _write_valid_spec(feature / "spec.md", status="Verified")
    _write_valid_plan(feature / "plan.md", status="Verified")
    _write_valid_tasks(feature / "tasks.md", status="Verified")
    _write_valid_verification(feature / "verification.md", status="Verified")
    _replace_section_body(
        feature / "verification.md",
        "## Spec compliance",
        (
            "```md",
            "| Acceptance criterion | Status | Evidence |",
            "|----------------------|--------|----------|",
            "| AC1 | Pass | `make check-all` exited 0. |",
            "```",
        ),
    )
    _replace_section_body(
        feature / "verification.md",
        "## Coverage",
        (
            "```md",
            "| metric | value | threshold | status |",
            "|--------|-------|-----------|--------|",
            "| line | 91% | >= 80% | Pass |",
            "```",
        ),
    )

    issues = validate_sdd_root(tmp_path)

    assert "verified-incomplete-spec-compliance" in _issue_codes(issues)
    assert "verified-coverage-incomplete" in _issue_codes(issues)


def test_required_sections_must_be_markdown_heading_lines(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-prose-heading-token")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    spec_path = feature / "spec.md"
    spec_text = spec_path.read_text(encoding="utf-8")
    spec_text = spec_text.replace(
        "The fixture spec is grounded by its own source record",
        "The fixture spec mentions `## Clarifications` in prose and is grounded by its own source record",
    )
    before_heading, after_heading = spec_text.rsplit("\n## Clarifications\n", 1)
    spec_text = before_heading + "\nClarifications\n" + after_heading
    spec_path.write_text(spec_text, encoding="utf-8")
    _write_valid_plan(feature / "plan.md", status="In Progress")
    _write_valid_tasks(feature / "tasks.md", status="In Progress", task_status="[~]")
    _write_valid_verification(feature / "verification.md", status="In Progress")

    issues = validate_sdd_root(tmp_path)

    assert "missing-gate-section" in _issue_codes(issues)
    messages = "\n".join(issue.message for issue in issues if issue.code == "missing-gate-section")
    assert "## Clarifications" in messages


def test_required_sections_ignore_fenced_heading_tokens(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-fenced-heading-token")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    spec_path = feature / "spec.md"
    spec_text = spec_path.read_text(encoding="utf-8")
    cited_sentence = (
        "The fixture spec is grounded by its own source record "
        f"(`{_feature_relative_dir(spec_path)}/spec.md:1`)."
    )
    spec_text = spec_text.replace(
        cited_sentence,
        "\n".join(
            [
                cited_sentence,
                "",
                "```text",
                "## Clarifications",
                "```",
            ]
        ),
    )
    before_heading, after_heading = spec_text.rsplit("\n## Clarifications\n", 1)
    spec_text = before_heading + "\nClarifications\n" + after_heading
    spec_path.write_text(spec_text, encoding="utf-8")
    _write_valid_plan(feature / "plan.md", status="In Progress")
    _write_valid_tasks(feature / "tasks.md", status="In Progress", task_status="[~]")
    _write_valid_verification(feature / "verification.md", status="In Progress")

    issues = validate_sdd_root(tmp_path)

    assert "missing-gate-section" in _issue_codes(issues)
    messages = "\n".join(issue.message for issue in issues if issue.code == "missing-gate-section")
    assert "## Clarifications" in messages


def test_required_sections_ignore_tilde_fenced_heading_tokens(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-tilde-fenced-heading-token")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    spec_path = feature / "spec.md"
    spec_text = spec_path.read_text(encoding="utf-8")
    cited_sentence = (
        "The fixture spec is grounded by its own source record "
        f"(`{_feature_relative_dir(spec_path)}/spec.md:1`)."
    )
    spec_text = spec_text.replace(
        cited_sentence,
        "\n".join(
            [
                cited_sentence,
                "",
                "~~~text",
                "## Clarifications",
                "~~~",
            ]
        ),
    )
    before_heading, after_heading = spec_text.rsplit("\n## Clarifications\n", 1)
    spec_text = before_heading + "\nClarifications\n" + after_heading
    spec_path.write_text(spec_text, encoding="utf-8")
    _write_valid_plan(feature / "plan.md", status="In Progress")
    _write_valid_tasks(feature / "tasks.md", status="In Progress", task_status="[~]")
    _write_valid_verification(feature / "verification.md", status="In Progress")

    issues = validate_sdd_root(tmp_path)

    assert "missing-gate-section" in _issue_codes(issues)
    messages = "\n".join(issue.message for issue in issues if issue.code == "missing-gate-section")
    assert "## Clarifications" in messages


def test_gate_evidence_rejects_single_cell_body_rows(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-single-cell-gate-evidence")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _replace_section_body(
        feature / "spec.md",
        "## Clarifications",
        (
            "| Question | Answer | Approved by | Approved at |",
            "|----------|",
            "| Decided by qinghuan on 2026-06-09 |",
        ),
    )
    _write_valid_plan(feature / "plan.md", status="In Progress")
    _write_valid_tasks(feature / "tasks.md", status="In Progress", task_status="[~]")
    _write_valid_verification(feature / "verification.md", status="In Progress")

    issues = validate_sdd_root(tmp_path)

    assert "gate-evidence-missing" in _issue_codes(issues)


def test_gate_evidence_rejects_tables_without_separator_rows(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-gate-evidence-without-separator")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _replace_section_body(
        feature / "spec.md",
        "## Clarifications",
        (
            "| Question | Answer | Approved by | Approved at |",
            "| Should malformed tables pass? | No. | qinghuan | 2026-06-09 |",
        ),
    )
    _write_valid_plan(feature / "plan.md", status="In Progress")
    _write_valid_tasks(feature / "tasks.md", status="In Progress", task_status="[~]")
    _write_valid_verification(feature / "verification.md", status="In Progress")

    issues = validate_sdd_root(tmp_path)

    assert "gate-evidence-missing" in _issue_codes(issues)


def test_gate_evidence_rejects_body_rows_before_separator(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-gate-evidence-pre-separator-body")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _replace_section_body(
        feature / "spec.md",
        "## Clarifications",
        (
            "| Question | Answer | Approved by | Approved at |",
            "| Should malformed tables pass? | No. | qinghuan | 2026-06-09 |",
            "|----------|--------|-------------|-------------|",
        ),
    )
    _write_valid_plan(feature / "plan.md", status="In Progress")
    _write_valid_tasks(feature / "tasks.md", status="In Progress", task_status="[~]")
    _write_valid_verification(feature / "verification.md", status="In Progress")

    issues = validate_sdd_root(tmp_path)

    assert "gate-evidence-missing" in _issue_codes(issues)


def test_gate_evidence_rejects_empty_separator_rows(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-gate-evidence-empty-separator")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _replace_section_body(
        feature / "spec.md",
        "## Clarifications",
        (
            "| Question | Answer | Approved by | Approved at |",
            "| | | | |",
            "| Should malformed tables pass? | No. | qinghuan | 2026-06-09 |",
        ),
    )
    _write_valid_plan(feature / "plan.md", status="In Progress")
    _write_valid_tasks(feature / "tasks.md", status="In Progress", task_status="[~]")
    _write_valid_verification(feature / "verification.md", status="In Progress")

    issues = validate_sdd_root(tmp_path)

    assert "gate-evidence-missing" in _issue_codes(issues)


def test_gate_evidence_rejects_repeated_separator_rows(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-gate-evidence-repeated-separator")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _replace_section_body(
        feature / "spec.md",
        "## Clarifications",
        (
            "| Question | Answer | Approved by | Approved at |",
            "|----------|--------|-------------|-------------|",
            "|----------|--------|-------------|-------------|",
            "| Should malformed tables pass? | No. | qinghuan | 2026-06-09 |",
        ),
    )
    _write_valid_plan(feature / "plan.md", status="In Progress")
    _write_valid_tasks(feature / "tasks.md", status="In Progress", task_status="[~]")
    _write_valid_verification(feature / "verification.md", status="In Progress")

    issues = validate_sdd_root(tmp_path)

    assert "gate-evidence-missing" in _issue_codes(issues)


def test_gate_evidence_rejects_repeated_header_rows(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-gate-evidence-repeated-header")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _replace_section_body(
        feature / "spec.md",
        "## Clarifications",
        (
            "| Question | Answer | Approved by | Approved at |",
            "|----------|--------|-------------|-------------|",
            "| Question | Answer | Approved by | Approved at |",
        ),
    )
    _write_valid_plan(feature / "plan.md", status="In Progress")
    _write_valid_tasks(feature / "tasks.md", status="In Progress", task_status="[~]")
    _write_valid_verification(feature / "verification.md", status="In Progress")

    issues = validate_sdd_root(tmp_path)

    assert "gate-evidence-missing" in _issue_codes(issues)


def test_gate_evidence_rejects_unclosed_table_rows(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-gate-evidence-unclosed-row")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _replace_section_body(
        feature / "spec.md",
        "## Clarifications",
        (
            "| Question | Answer | Approved by | Approved at |",
            "|----------|--------|-------------|-------------|",
            "| Should malformed tables pass? | No. | qinghuan | 2026-06-09",
        ),
    )
    _write_valid_plan(feature / "plan.md", status="In Progress")
    _write_valid_tasks(feature / "tasks.md", status="In Progress", task_status="[~]")
    _write_valid_verification(feature / "verification.md", status="In Progress")

    issues = validate_sdd_root(tmp_path)

    assert "gate-evidence-missing" in _issue_codes(issues)


def test_gate_evidence_rejects_doubled_boundary_pipes(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-gate-evidence-doubled-boundary")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _replace_section_body(
        feature / "spec.md",
        "## Clarifications",
        (
            "|| Question | Answer | Approved by | Approved at ||",
            "||----------|--------|-------------|-------------||",
            "|| Should malformed tables pass? | No. | qinghuan | 2026-06-09 ||",
        ),
    )
    _write_valid_plan(feature / "plan.md", status="In Progress")
    _write_valid_tasks(feature / "tasks.md", status="In Progress", task_status="[~]")
    _write_valid_verification(feature / "verification.md", status="In Progress")

    issues = validate_sdd_root(tmp_path)

    assert "gate-evidence-missing" in _issue_codes(issues)


def test_gate_evidence_rejects_indented_table_rows(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-gate-evidence-indented-table")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _replace_section_body(
        feature / "spec.md",
        "## Clarifications",
        (
            "    | Question | Answer | Approved by | Approved at |",
            "    |----------|--------|-------------|-------------|",
            "    | Should indented tables pass? | No. | qinghuan | 2026-06-09 |",
        ),
    )
    _write_valid_plan(feature / "plan.md", status="In Progress")
    _write_valid_tasks(feature / "tasks.md", status="In Progress", task_status="[~]")
    _write_valid_verification(feature / "verification.md", status="In Progress")

    issues = validate_sdd_root(tmp_path)

    assert "gate-evidence-missing" in _issue_codes(issues)


def test_gate_evidence_rejects_separator_arity_mismatch(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-gate-evidence-separator-arity")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _replace_section_body(
        feature / "spec.md",
        "## Clarifications",
        (
            "| Question | Answer | Approved by | Approved at |",
            "|----------|--------|",
            "| Should malformed tables pass? | No. | qinghuan | 2026-06-09 |",
        ),
    )
    _write_valid_plan(feature / "plan.md", status="In Progress")
    _write_valid_tasks(feature / "tasks.md", status="In Progress", task_status="[~]")
    _write_valid_verification(feature / "verification.md", status="In Progress")

    issues = validate_sdd_root(tmp_path)

    assert "gate-evidence-missing" in _issue_codes(issues)


def test_gate_evidence_rejects_body_row_arity_mismatch(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-gate-evidence-body-arity")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _replace_section_body(
        feature / "spec.md",
        "## Clarifications",
        (
            "| Question | Answer | Approved by | Approved at |",
            "|----------|--------|-------------|-------------|",
            "| Should malformed tables pass? | No. | qinghuan |",
        ),
    )
    _write_valid_plan(feature / "plan.md", status="In Progress")
    _write_valid_tasks(feature / "tasks.md", status="In Progress", task_status="[~]")
    _write_valid_verification(feature / "verification.md", status="In Progress")

    issues = validate_sdd_root(tmp_path)

    assert "gate-evidence-missing" in _issue_codes(issues)


def test_gate_evidence_rejects_non_contiguous_body_rows(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-gate-evidence-non-contiguous")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _replace_section_body(
        feature / "spec.md",
        "## Clarifications",
        (
            "| Question | Answer | Approved by | Approved at |",
            "|----------|--------|-------------|-------------|",
            "Body rows below this prose are not part of the Markdown table.",
            "| Should malformed tables pass? | No. | qinghuan | 2026-06-09 |",
        ),
    )
    _write_valid_plan(feature / "plan.md", status="In Progress")
    _write_valid_tasks(feature / "tasks.md", status="In Progress", task_status="[~]")
    _write_valid_verification(feature / "verification.md", status="In Progress")

    issues = validate_sdd_root(tmp_path)

    assert "gate-evidence-missing" in _issue_codes(issues)


def test_gate_evidence_rejects_wrong_clarification_header(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-gate-evidence-wrong-header")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _replace_section_body(
        feature / "spec.md",
        "## Clarifications",
        (
            "| Topic | Decision | Owner | Date |",
            "|-------|----------|-------|------|",
            "| Gate schema | Must be canonical. | qinghuan | 2026-06-09 |",
        ),
    )
    _write_valid_plan(feature / "plan.md", status="In Progress")
    _write_valid_tasks(feature / "tasks.md", status="In Progress", task_status="[~]")
    _write_valid_verification(feature / "verification.md", status="In Progress")

    issues = validate_sdd_root(tmp_path)

    assert "gate-evidence-missing" in _issue_codes(issues)


def test_clarification_gate_evidence_rejects_non_canonical_approval_dates(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-non-canonical-clarification-approval")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _replace_section_body(
        feature / "spec.md",
        "## Clarifications",
        (
            "| Question | Answer | Approved by | Approved at |",
            "|----------|--------|-------------|-------------|",
            "| Scope? | Harness only. | qinghuan | 20260609 |",
        ),
    )
    _write_valid_plan(feature / "plan.md", status="In Progress")
    _write_valid_tasks(feature / "tasks.md", status="In Progress", task_status="[~]")
    _write_valid_verification(feature / "verification.md", status="In Progress")

    issues = validate_sdd_root(tmp_path)

    assert "gate-evidence-missing" in _issue_codes(issues)


def test_gate_compliance_requires_all_canonical_gate_rows(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-incomplete-gate-compliance")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _write_valid_plan(feature / "plan.md", status="In Progress")
    _write_valid_tasks(feature / "tasks.md", status="In Progress", task_status="[~]")
    _replace_section_body(
        feature / "tasks.md",
        "## Gate Compliance",
        (
            "| Gate | Evidence |",
            "|------|----------|",
            "| Clarify | `spec.md` includes `## Clarifications`. |",
            "| Checklist | `spec.md` includes `## Requirement Checklist`. |",
            "| Analyze | `plan.md` includes `## Analyze Gate`. |",
        ),
    )
    _write_valid_verification(feature / "verification.md", status="In Progress")

    issues = validate_sdd_root(tmp_path)

    assert "gate-evidence-missing" in _issue_codes(issues)


def test_gate_compliance_rejects_duplicate_gate_rows(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-duplicated-gate-compliance")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _write_valid_plan(feature / "plan.md", status="In Progress")
    _write_valid_tasks(feature / "tasks.md", status="In Progress", task_status="[~]")
    _replace_section_body(
        feature / "tasks.md",
        "## Gate Compliance",
        (
            "| Gate | Evidence |",
            "|------|----------|",
            "| Clarify | `spec.md` includes `## Clarifications`. |",
            "| Clarify | duplicate copied row. |",
            "| Checklist | `spec.md` includes `## Requirement Checklist`. |",
            "| Analyze | `plan.md` includes `## Analyze Gate`. |",
            "| Implement | Tasks below are TDD ordered. |",
            "| Verify | `verification.md` captures command output. |",
        ),
    )
    _write_valid_verification(feature / "verification.md", status="In Progress")

    issues = validate_sdd_root(tmp_path)

    assert "gate-evidence-missing" in _issue_codes(issues)


def test_gate_compliance_rejects_split_table_blocks(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-split-gate-compliance")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _write_valid_plan(feature / "plan.md", status="In Progress")
    _write_valid_tasks(feature / "tasks.md", status="In Progress", task_status="[~]")
    _replace_section_body(
        feature / "tasks.md",
        "## Gate Compliance",
        (
            "| Gate | Evidence |",
            "|------|----------|",
            "| Clarify | `spec.md` includes `## Clarifications`. |",
            "| Checklist | `spec.md` includes `## Requirement Checklist`. |",
            "",
            "Split lifecycle evidence must not be stitched together.",
            "",
            "| Gate | Evidence |",
            "|------|----------|",
            "| Analyze | `plan.md` includes `## Analyze Gate`. |",
            "| Implement | Tasks below are TDD ordered. |",
            "| Verify | `verification.md` captures command output. |",
        ),
    )
    _write_valid_verification(feature / "verification.md", status="In Progress")

    issues = validate_sdd_root(tmp_path)

    assert "gate-evidence-missing" in _issue_codes(issues)


def test_plan_analyze_gate_rejects_failed_results(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-failed-analyze-gate")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _write_valid_plan(feature / "plan.md", status="In Progress")
    _replace_section_body(
        feature / "plan.md",
        "## Analyze Gate",
        (
            "| Check | Result |",
            "|-------|--------|",
            "| Architecture boundary is proven. | Fail: source audit found a conflicting owner. |",
        ),
    )
    _write_valid_tasks(feature / "tasks.md", status="In Progress", task_status="[~]")
    _write_valid_verification(feature / "verification.md", status="In Progress")

    issues = validate_sdd_root(tmp_path)

    assert "plan-analyze-gate-invalid" in _issue_codes(issues)


def test_plan_analyze_gate_rejects_status_without_evidence(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-analyze-gate-status-without-evidence")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _write_valid_plan(feature / "plan.md", status="In Progress")
    _replace_section_body(
        feature / "plan.md",
        "## Analyze Gate",
        (
            "| Check | Result |",
            "|-------|--------|",
            "| Architecture boundary is proven. | Pass: |",
        ),
    )
    _write_valid_tasks(feature / "tasks.md", status="In Progress", task_status="[~]")
    _write_valid_verification(feature / "verification.md", status="In Progress")

    issues = validate_sdd_root(tmp_path)

    assert "plan-analyze-gate-invalid" in _issue_codes(issues)


def test_plan_analyze_gate_ignores_non_canonical_tables(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-analyze-gate-extra-table")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _write_valid_plan(feature / "plan.md", status="In Progress")
    _replace_section_body(
        feature / "plan.md",
        "## Analyze Gate",
        (
            "| Check | Result |",
            "|-------|--------|",
            "| Architecture boundary is proven. | Pass: source audit is captured. |",
            "",
            "| Note | Value |",
            "|------|-------|",
            "| Non-gate example | This table is context, not an Analyze Gate result. |",
        ),
    )
    _write_valid_tasks(feature / "tasks.md", status="In Progress", task_status="[~]")
    _write_valid_verification(feature / "verification.md", status="In Progress")

    issues = validate_sdd_root(tmp_path)

    assert "plan-analyze-gate-invalid" not in _issue_codes(issues)


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


def test_acceptance_criteria_require_when_then_shall_format(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-vague-ac")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _replace_acceptance_criterion(feature / "spec.md", 1, "AC1. Improve the harness.")
    _write_valid_plan(feature / "plan.md", status="In Progress")
    _write_valid_tasks(feature / "tasks.md", status="In Progress", task_status="[~]")
    _write_valid_verification(feature / "verification.md", status="In Progress")

    issues = validate_sdd_root(tmp_path)

    assert "acceptance-criterion-format-invalid" in _issue_codes(issues)


def test_acceptance_criteria_must_live_in_acceptance_section(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-ac-outside-section")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _replace_section_body(
        feature / "spec.md",
        "## Acceptance criteria",
        (
            "_No current acceptance criteria here._",
            "",
            "## Appendix",
            "",
            "- AC1. WHEN stale appendix evidence exists THEN the harness SHALL ignore it.",
        ),
    )
    _write_valid_plan(feature / "plan.md", status="In Progress")
    _write_valid_tasks(feature / "tasks.md", status="In Progress", task_status="[~]")
    _write_valid_verification(feature / "verification.md", status="In Progress")

    issues = validate_sdd_root(tmp_path)

    assert "acceptance-numbering-invalid" in _issue_codes(issues)


def test_plan_acceptance_commands_must_live_in_acceptance_section(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-command-outside-section")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _write_valid_plan(feature / "plan.md", status="In Progress")
    _replace_section_body(
        feature / "plan.md",
        "## Acceptance test commands",
        (
            "_No current acceptance commands here._",
            "",
            "## Appendix",
            "",
            "- AC1: `uv run pytest tests/architecture/test_sdd_artifact_validator.py`",
        ),
    )
    _write_valid_tasks(feature / "tasks.md", status="In Progress", task_status="[~]")
    _write_valid_verification(feature / "verification.md", status="In Progress")

    issues = validate_sdd_root(tmp_path)

    assert "acceptance-command-mismatch" in _issue_codes(issues)
    assert any("missing commands for AC1" in issue.message for issue in issues)


def test_spec_requires_at_least_one_acceptance_criterion(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-empty-acceptance")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _replace_section_body(
        feature / "spec.md",
        "## Acceptance criteria",
        ("_No current acceptance criteria here._",),
    )
    _write_valid_plan(feature / "plan.md", status="In Progress")
    _replace_section_body(
        feature / "plan.md",
        "## Acceptance test commands",
        ("_No current acceptance commands here._",),
    )
    _write_valid_tasks(feature / "tasks.md", status="In Progress", task_status="[~]")
    _write_valid_verification(feature / "verification.md", status="In Progress")

    issues = validate_sdd_root(tmp_path)

    assert "acceptance-numbering-invalid" in _issue_codes(issues)


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


def test_plan_acceptance_commands_reject_trailing_prose(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-trailing-prose-ac-command")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _write_valid_plan(feature / "plan.md", status="In Progress")
    _replace_acceptance_command_line(
        feature / "plan.md",
        1,
        "- AC1: `uv run pytest tests/architecture/test_sdd_artifact_validator.py` or equivalent",
    )
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


def test_superseded_feature_requires_canonical_artifact_sections(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "completed", "2026-06-09-superseded-stale-sections")
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
    spec_path = feature / "spec.md"
    spec_path.write_text(
        spec_path.read_text(encoding="utf-8").replace("## Acceptance criteria", "## Acceptance Criteria"),
        encoding="utf-8",
    )

    issues = validate_sdd_root(tmp_path)

    assert "missing-gate-section" in _issue_codes(issues)
    assert "Acceptance criteria" in "\n".join(issue.message for issue in issues)


def test_superseded_feature_rejects_acceptance_command_drift(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "completed", "2026-06-09-superseded-command-drift")
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
    _append_acceptance_criterion(feature / "spec.md", 2)

    issues = validate_sdd_root(tmp_path)

    assert "acceptance-command-mismatch" in _issue_codes(issues)
    assert "AC2" in "\n".join(issue.message for issue in issues)


def test_active_feature_rejects_unbounded_task_board(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-unbounded-active-record")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _write_valid_plan(feature / "plan.md", status="In Progress")
    _write_valid_tasks(feature / "tasks.md", status="In Progress", task_status="[~]")
    _write_valid_verification(feature / "verification.md", status="In Progress")
    tasks_path = feature / "tasks.md"
    tasks_text = tasks_path.read_text(encoding="utf-8")
    for task_number in range(2, 42):
        tasks_text += (
            f"\n\n### Task {task_number} - Bounded slice {task_number}\n\n"
            "- **File(s)**: `tests/architecture/test_sdd_artifact_validator.py`, "
            "`scripts/validate_sdd_artifacts.py`\n"
            "- **Owner**: parent\n"
            f"- **Depends on**: Task {task_number - 1}\n"
            "- **Touch set**: `scripts/validate_sdd_artifacts.py`\n"
            "- **Conflict set**: `scripts/regen_sdd_work_index.py`\n"
            "- **Failing test first**: `tests/architecture/test_sdd_artifact_validator.py::"
            "test_active_feature_rejects_unbounded_task_board` - asserts active records stay bounded.\n"
            "- **Subagent handoff**: not delegated\n"
            "- **Subagent report**: not delegated\n"
            "- **Review result**: parent-reviewed\n"
            "- **Factory lane**: Harness/tests\n"
            "- **Deterministic constraints**: Active features stay small enough for a single agent loop.\n"
            "- **On-demand context**: `docs/sdd/README.md`, `scripts/validate_sdd_artifacts.py`.\n"
            "- **Kill/defer criteria**: Stop if active records must remain omnibus ledgers.\n"
            "- **Eval/repair signal**: `active-feature-too-large`.\n"
            "- **Implementation**: Keep active work in bounded slices.\n"
            "- **Verification**: `uv run pytest tests/architecture/test_sdd_artifact_validator.py -q`\n"
            "- **Review owner**: parent\n"
            "- **Status**: [~]\n"
        )
    tasks_path.write_text(tasks_text, encoding="utf-8")

    issues = validate_sdd_root(tmp_path)

    assert "active-feature-too-large" in _issue_codes(issues)
    assert "41 task" in "\n".join(issue.message for issue in issues)


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


def test_verified_feature_requires_make_check_all_own_exit_code_zero(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "completed", "2026-06-09-check-all-own-exit")
    helper_command = "python -c 'print(\"helper\")'"
    _write_valid_spec(feature / "spec.md", status="Verified")
    _write_valid_plan(feature / "plan.md", status="Verified")
    _write_valid_tasks(feature / "tasks.md", status="Verified")
    _write_valid_verification(
        feature / "verification.md",
        status="Verified",
        verification_command_lines=(
            "$ make check-all",
            "tests failed",
            "exit code: 2",
            f"$ {helper_command}",
            "helper",
            "exit code: 0",
        ),
    )
    _replace_spec_compliance_row(
        feature / "verification.md",
        f"| AC1 | Pass | `{helper_command}` exited 0. |",
    )

    issues = validate_sdd_root(tmp_path)

    assert "verified-missing-check-all" in _issue_codes(issues)
    assert "verified-contradicts-evidence" in _issue_codes(issues)


def test_verified_feature_rejects_multiple_check_all_exit_codes(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "completed", "2026-06-09-check-all-multiple-exits")
    helper_command = "uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_helper -q"
    _write_valid_spec(feature / "spec.md", status="Verified")
    _write_valid_plan(feature / "plan.md", status="Verified")
    _write_valid_tasks(feature / "tasks.md", status="Verified", verification=helper_command)
    _write_valid_verification(
        feature / "verification.md",
        status="Verified",
        verification_command_lines=(
            "$ make check-all",
            "integration failed",
            "exit code: 1",
            "rerun succeeded",
            "exit code: 0",
        ),
        other_command_lines=(
            f"$ {helper_command}",
            "1 passed in 0.01s",
            "exit code: 0",
        ),
    )
    _replace_spec_compliance_row(
        feature / "verification.md",
        f"| AC1 | Pass | `{helper_command}` exited 0. |",
    )

    issues = validate_sdd_root(tmp_path)

    assert "verified-missing-check-all" in _issue_codes(issues)
    assert "verified-contradicts-evidence" in _issue_codes(issues)
    assert "exactly one exit code 0" in "\n".join(issue.message for issue in issues)


def test_verified_feature_rejects_positive_skipped_test_count(tmp_path: Path) -> None:
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


def test_verified_feature_rejects_positive_skipped_count_with_placeholder_reason(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "completed", "2026-06-09-placeholder-skip-reason")
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
            "| 1 | Pending | Yes |",
        ),
    )

    issues = validate_sdd_root(tmp_path)

    assert "verified-unexplained-skips" in _issue_codes(issues)
    assert "zero skipped tests" in "\n".join(issue.message for issue in issues)


def test_verified_feature_rejects_positive_skipped_test_count_with_freeform_table(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "completed", "2026-06-09-freeform-skip-table")
    _write_valid_spec(feature / "spec.md", status="Verified")
    _write_valid_plan(feature / "plan.md", status="Verified")
    _write_valid_tasks(feature / "tasks.md", status="Verified")
    _write_valid_verification(
        feature / "verification.md",
        status="Verified",
        skipped_count="1",
        skipped_table_rows=(
            "| qty | note | ok |",
            "| 1 | existing skip | Yes |",
        ),
    )

    issues = validate_sdd_root(tmp_path)

    assert "verified-unexplained-skips" in _issue_codes(issues)
    assert "zero skipped tests" in "\n".join(issue.message for issue in issues)


def test_verified_feature_requires_numeric_skipped_test_count(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "completed", "2026-06-09-pending-skip-count")
    _write_valid_spec(feature / "spec.md", status="Verified")
    _write_valid_plan(feature / "plan.md", status="Verified")
    _write_valid_tasks(feature / "tasks.md", status="Verified")
    _write_valid_verification(feature / "verification.md", status="Verified", skipped_count="Pending")

    issues = validate_sdd_root(tmp_path)

    assert "verified-unexplained-skips" in _issue_codes(issues)
    assert "numeric skipped-test count" in "\n".join(issue.message for issue in issues)


def test_verified_feature_requires_skipped_count_inside_skipped_tests_section(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "completed", "2026-06-09-stale-skip-count")
    _write_valid_spec(feature / "spec.md", status="Verified")
    _write_valid_plan(feature / "plan.md", status="Verified")
    _write_valid_tasks(feature / "tasks.md", status="Verified")
    _write_valid_verification(
        feature / "verification.md",
        status="Verified",
        skipped_count="Pending",
        other_command_lines=(
            "$ uv run pytest tests/architecture/test_sdd_artifact_validator.py -q",
            "Number of skipped tests in the run above: 0",
            "1 passed in 0.01s",
            "exit code: 0",
        ),
    )

    issues = validate_sdd_root(tmp_path)

    assert "verified-unexplained-skips" in _issue_codes(issues)
    assert "Skipped tests section" in "\n".join(issue.message for issue in issues)


def test_verified_feature_requires_complete_spec_compliance_rows(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "completed", "2026-06-09-incomplete-spec-compliance")
    _write_valid_spec(feature / "spec.md", status="Verified")
    _write_valid_plan(feature / "plan.md", status="Verified")
    _write_valid_tasks(feature / "tasks.md", status="Verified")
    _write_valid_verification(feature / "verification.md", status="Verified")
    verification_path = feature / "verification.md"
    verification_text = verification_path.read_text(encoding="utf-8")
    verification_path.write_text(
        verification_text.replace("| AC1 | Pass | `make check-all` exited 0. |", "| AC1 | In Progress | Pending. |"),
        encoding="utf-8",
    )

    issues = validate_sdd_root(tmp_path)

    assert "verified-incomplete-spec-compliance" in _issue_codes(issues)
    assert "AC1" in "\n".join(issue.message for issue in issues)


def test_verified_feature_rejects_symbolic_completion_status_tokens(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "completed", "2026-06-09-symbolic-status")
    _write_valid_spec(feature / "spec.md", status="Verified")
    _write_valid_plan(feature / "plan.md", status="Verified")
    _write_valid_tasks(feature / "tasks.md", status="Verified")
    _write_valid_verification(feature / "verification.md", status="Verified")
    verification_path = feature / "verification.md"
    verification_text = verification_path.read_text(encoding="utf-8")
    verification_path.write_text(
        verification_text.replace(
            "| AC1 | Pass | `make check-all` exited 0. |",
            "| AC1 | ✅ | `make check-all` exited 0. |",
        )
        .replace("| line | 91% | >= 80% | Pass |", "| line | 91% | >= 80% | ✅ |"),
        encoding="utf-8",
    )

    issues = validate_sdd_root(tmp_path)

    assert "verified-incomplete-spec-compliance" in _issue_codes(issues)
    assert "verified-coverage-incomplete" in _issue_codes(issues)


def test_verification_tables_reject_symbolic_status_tokens_before_final_verification(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-symbolic-active-status")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _write_valid_plan(feature / "plan.md", status="In Progress")
    _write_valid_tasks(feature / "tasks.md", status="In Progress")
    _write_valid_verification(feature / "verification.md", status="In Progress")
    verification_path = feature / "verification.md"
    verification_text = verification_path.read_text(encoding="utf-8")
    verification_path.write_text(
        verification_text.replace(
            "| AC1 | Pass | `make check-all` exited 0. |",
            "| AC1 | ✅ | `make check-all` exited 0. |",
        )
        .replace("| line | 91% | >= 80% | Pass |", "| line | 91% | >= 80% | ❌ |"),
        encoding="utf-8",
    )

    issues = validate_sdd_root(tmp_path)

    assert "verification-status-token-invalid" in _issue_codes(issues)
    assert "Spec compliance" in "\n".join(issue.message for issue in issues)
    assert "Coverage" in "\n".join(issue.message for issue in issues)


def test_active_records_reject_legacy_sdd_lifecycle_check_flags(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-legacy-sdd-check")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _write_valid_plan(feature / "plan.md", status="In Progress")
    _write_valid_tasks(
        feature / "tasks.md",
        status="In Progress",
        verification="uv run python scripts/validate_sdd_artifacts.py --check",
    )
    _write_valid_verification(
        feature / "verification.md",
        status="In Progress",
        other_command_lines=(
            "$ uv run python scripts/check_sdd_gate.py --all-active --check",
            "all active SDD gates passed",
            "exit code: 0",
        ),
    )

    issues = validate_sdd_root(tmp_path)

    assert "active-sdd-lifecycle-check-flag-invalid" in _issue_codes(issues)
    assert "validate_sdd_artifacts.py --check" in "\n".join(issue.message for issue in issues)
    assert "check_sdd_gate.py --all-active --check" in "\n".join(issue.message for issue in issues)


def test_active_records_reject_placeholder_final_verification_transcripts(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-placeholder-final-transcript")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _write_valid_plan(feature / "plan.md", status="In Progress")
    _write_valid_tasks(feature / "tasks.md", status="In Progress")
    _write_valid_verification(
        feature / "verification.md",
        status="In Progress",
        verification_command_lines=(
            "$ make check-all",
            "Pending final run.",
            "exit code: pending",
        ),
    )

    issues = validate_sdd_root(tmp_path)

    messages = "\n".join(issue.message for issue in issues).lower()
    assert "active-placeholder-final-evidence" in _issue_codes(issues)
    assert "pending final run" in messages
    assert "exit code: pending" in messages


def test_active_records_reject_template_placeholder_final_verification_transcripts(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-template-final-transcript")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _write_valid_plan(feature / "plan.md", status="In Progress")
    _write_valid_tasks(feature / "tasks.md", status="In Progress")
    _write_valid_verification(
        feature / "verification.md",
        status="In Progress",
        verification_command_lines=(
            "$ make check-all",
            "<paste full stdout/stderr here>",
            "exit code: 0",
        ),
    )

    issues = validate_sdd_root(tmp_path)

    messages = "\n".join(issue.message for issue in issues).lower()
    assert "active-placeholder-final-evidence" in _issue_codes(issues)
    assert "<paste full stdout/stderr here>" in messages


def test_active_records_reject_skipped_count_without_final_evidence(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-stale-active-skip-count")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _write_valid_plan(feature / "plan.md", status="In Progress")
    _write_valid_tasks(feature / "tasks.md", status="In Progress")
    _write_valid_verification(
        feature / "verification.md",
        status="In Progress",
        verification_command_lines=(
            "$ uv run pytest tests/architecture/test_sdd_artifact_validator.py -q",
            "1 passed in 0.01s",
            "exit code: 0",
        ),
    )

    issues = validate_sdd_root(tmp_path)

    assert "active-skipped-count-without-final-evidence" in _issue_codes(issues)
    assert "Skipped tests" in "\n".join(issue.message for issue in issues)


def test_verified_feature_requires_concrete_spec_compliance_evidence(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "completed", "2026-06-09-placeholder-spec-evidence")
    _write_valid_spec(feature / "spec.md", status="Verified")
    _write_valid_plan(feature / "plan.md", status="Verified")
    _write_valid_tasks(feature / "tasks.md", status="Verified")
    _write_valid_verification(feature / "verification.md", status="Verified")
    verification_path = feature / "verification.md"
    verification_text = verification_path.read_text(encoding="utf-8")
    verification_path.write_text(
        verification_text.replace("| AC1 | Pass | `make check-all` exited 0. |", "| AC1 | Pass | Pending. |"),
        encoding="utf-8",
    )

    issues = validate_sdd_root(tmp_path)

    assert "verified-incomplete-spec-compliance" in _issue_codes(issues)
    assert "evidence" in "\n".join(issue.message for issue in issues)


def test_verified_feature_requires_command_shaped_spec_compliance_evidence(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "completed", "2026-06-09-prose-spec-evidence")
    _write_valid_spec(feature / "spec.md", status="Verified")
    _write_valid_plan(feature / "plan.md", status="Verified")
    _write_valid_tasks(feature / "tasks.md", status="Verified")
    _write_valid_verification(feature / "verification.md", status="Verified")
    verification_path = feature / "verification.md"
    verification_text = verification_path.read_text(encoding="utf-8")
    verification_path.write_text(
        verification_text.replace(
            "| AC1 | Pass | `make check-all` exited 0. |",
            "| AC1 | Pass | Manual review completed. |",
        ),
        encoding="utf-8",
    )

    issues = validate_sdd_root(tmp_path)

    assert "verified-missing-spec-compliance-evidence" in _issue_codes(issues)
    assert "command-shaped evidence" in "\n".join(issue.message for issue in issues)


def test_verified_feature_requires_spec_compliance_rows(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "completed", "2026-06-09-empty-spec-compliance")
    _write_valid_spec(feature / "spec.md", status="Verified")
    _write_valid_plan(feature / "plan.md", status="Verified")
    _write_valid_tasks(feature / "tasks.md", status="Verified")
    _write_valid_verification(feature / "verification.md", status="Verified")
    _replace_section_body(
        feature / "verification.md",
        "## Spec compliance",
        (
            "| Acceptance criterion | Status | Evidence |",
            "|----------------------|--------|----------|",
        ),
    )

    issues = validate_sdd_root(tmp_path)

    assert "verified-incomplete-spec-compliance" in _issue_codes(issues)
    assert "Spec compliance" in "\n".join(issue.message for issue in issues)


def test_verified_feature_requires_spec_compliance_for_all_acceptance_criteria(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "completed", "2026-06-09-partial-spec-compliance")
    _write_valid_spec(feature / "spec.md", status="Verified")
    _append_acceptance_criterion(feature / "spec.md", 2)
    _write_valid_plan(feature / "plan.md", status="Verified")
    _append_acceptance_command(feature / "plan.md", 2)
    _write_valid_tasks(feature / "tasks.md", status="Verified")
    _write_valid_verification(feature / "verification.md", status="Verified")

    issues = validate_sdd_root(tmp_path)

    assert "verified-incomplete-spec-compliance" in _issue_codes(issues)
    assert "missing AC2" in "\n".join(issue.message for issue in issues)


def test_verified_feature_requires_passing_coverage_rows(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "completed", "2026-06-09-pending-coverage")
    _write_valid_spec(feature / "spec.md", status="Verified")
    _write_valid_plan(feature / "plan.md", status="Verified")
    _write_valid_tasks(feature / "tasks.md", status="Verified")
    _write_valid_verification(feature / "verification.md", status="Verified")
    verification_path = feature / "verification.md"
    verification_text = verification_path.read_text(encoding="utf-8")
    verification_path.write_text(
        verification_text.replace("| line | 91% | >= 80% | Pass |", "| line | Pending | >= 80% | Pending |"),
        encoding="utf-8",
    )

    issues = validate_sdd_root(tmp_path)

    assert "verified-coverage-incomplete" in _issue_codes(issues)
    assert "line" in "\n".join(issue.message for issue in issues)


def test_verified_feature_requires_concrete_coverage_values(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "completed", "2026-06-09-placeholder-coverage-value")
    _write_valid_spec(feature / "spec.md", status="Verified")
    _write_valid_plan(feature / "plan.md", status="Verified")
    _write_valid_tasks(feature / "tasks.md", status="Verified")
    _write_valid_verification(feature / "verification.md", status="Verified")
    verification_path = feature / "verification.md"
    verification_text = verification_path.read_text(encoding="utf-8")
    verification_path.write_text(
        verification_text.replace("| line | 91% | >= 80% | Pass |", "| line | Pending | >= 80% | Pass |"),
        encoding="utf-8",
    )

    issues = validate_sdd_root(tmp_path)

    assert "verified-coverage-incomplete" in _issue_codes(issues)
    assert "value" in "\n".join(issue.message for issue in issues)


def test_verified_feature_requires_complete_e2e_golden_path(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "completed", "2026-06-09-incomplete-e2e-golden")
    _write_valid_spec(feature / "spec.md", status="Verified")
    _write_valid_plan(feature / "plan.md", status="Verified")
    _write_valid_tasks(feature / "tasks.md", status="Verified")
    _write_valid_verification(feature / "verification.md", status="Verified")
    verification_path = feature / "verification.md"
    verification_text = verification_path.read_text(encoding="utf-8")
    verification_path.write_text(
        verification_text.replace("- [x] WS /ws/live pushed within 5s", "- [ ] WS /ws/live pushed within 5s"),
        encoding="utf-8",
    )

    issues = validate_sdd_root(tmp_path)

    assert "verified-e2e-incomplete" in _issue_codes(issues)
    assert "WS /ws/live" in "\n".join(issue.message for issue in issues)


def test_verified_feature_rejects_fenced_e2e_golden_path(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "completed", "2026-06-09-fenced-e2e-golden")
    _write_valid_spec(feature / "spec.md", status="Verified")
    _write_valid_plan(feature / "plan.md", status="Verified")
    _write_valid_tasks(feature / "tasks.md", status="Verified")
    _write_valid_verification(feature / "verification.md", status="Verified")
    verification_path = feature / "verification.md"
    verification_text = verification_path.read_text(encoding="utf-8")
    checklist = "\n".join(
        [
            "- [x] /readyz returned 200",
            "- [x] writer wrote a row visible to a separate process",
            "- [x] /api/recent returned the injected event",
            "- [x] WS /ws/live pushed within 5s",
            "- [x] testcontainers PG and uvicorn subprocess cleaned up",
        ]
    )
    verification_path.write_text(
        verification_text.replace(checklist, f"```text\n{checklist}\n```"),
        encoding="utf-8",
    )

    issues = validate_sdd_root(tmp_path)

    assert "verified-e2e-incomplete" in _issue_codes(issues)


def test_verified_feature_rejects_golden_skip_switch(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "completed", "2026-06-09-skip-golden")
    _write_valid_spec(feature / "spec.md", status="Verified")
    _write_valid_plan(feature / "plan.md", status="Verified")
    _write_valid_tasks(feature / "tasks.md", status="Verified")
    _write_valid_verification(feature / "verification.md", status="Verified")
    verification_path = feature / "verification.md"
    verification_text = verification_path.read_text(encoding="utf-8")
    verification_path.write_text(
        verification_text.replace(
            "- [x] testcontainers PG and uvicorn subprocess cleaned up",
            "- [x] testcontainers PG and uvicorn subprocess cleaned up\n"
            "- [x] SKIP_GOLDEN=1 bypassed the golden lane",
        ),
        encoding="utf-8",
    )

    issues = validate_sdd_root(tmp_path)

    assert "verified-e2e-incomplete" in _issue_codes(issues)
    assert "SKIP_GOLDEN" in "\n".join(issue.message for issue in issues)


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


def test_validator_cli_fails_on_issues_without_check_flag(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-cli-soft-mode")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _write_valid_plan(feature / "plan.md", status="In Progress")
    _write_valid_tasks(
        feature / "tasks.md",
        status="In Progress",
        verification="uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_expected_gate -q",
        task_status="[x]",
    )
    _write_valid_verification(feature / "verification.md", status="In Progress")

    assert main(["--root", str(tmp_path)]) == 1


def test_validator_cli_rejects_legacy_check_flag() -> None:
    with pytest.raises(SystemExit) as exc:
        main(["--check"])

    assert exc.value.code == 2


def test_complete_tasks_require_failing_test_reference_evidence(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-complete-task-without-red-coverage")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _write_valid_plan(feature / "plan.md", status="In Progress")
    _write_valid_tasks(
        feature / "tasks.md",
        status="In Progress",
        failing_test_first=(
            "tests/architecture/test_never_ran.py::test_missing_red - asserts missing RED coverage."
        ),
        verification="uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_expected_gate -q",
        task_status="[x]",
    )
    _write_valid_verification(
        feature / "verification.md",
        status="In Progress",
        other_command_lines=(
            "$ uv run pytest tests/architecture/test_sdd_artifact_validator.py::test_expected_gate -q",
            "1 passed in 0.01s",
            "exit code: 0",
        ),
    )

    issues = validate_sdd_root(tmp_path)

    assert "task-complete-missing-failing-test-evidence" in _issue_codes(issues)


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


def test_tasks_reject_fenced_task_sections(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-fenced-task-section")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _write_valid_plan(feature / "plan.md", status="In Progress")
    _write_valid_tasks(feature / "tasks.md", status="In Progress", task_status="[~]")
    _move_only_task_into_fenced_block(feature / "tasks.md")
    _write_valid_verification(feature / "verification.md", status="In Progress")

    issues = validate_sdd_root(tmp_path)

    assert "task-missing-coordination-fields" in _issue_codes(issues)
    assert "task-missing-agent-loop-fields" in _issue_codes(issues)


def test_tasks_must_live_inside_tasks_section(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-task-outside-section")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _write_valid_plan(feature / "plan.md", status="In Progress")
    _write_valid_tasks(feature / "tasks.md", status="In Progress", task_status="[~]")
    _move_only_task_after_tasks_section(feature / "tasks.md")
    _write_valid_verification(feature / "verification.md", status="In Progress")

    issues = validate_sdd_root(tmp_path)

    assert "task-missing-coordination-fields" in _issue_codes(issues)
    assert "task-missing-agent-loop-fields" in _issue_codes(issues)


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


def test_tasks_reject_missing_current_file_and_touch_paths(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-missing-current-touch-path")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _write_valid_plan(feature / "plan.md", status="In Progress")
    _write_valid_tasks(
        feature / "tasks.md",
        status="In Progress",
        touch_set="stale-root-artifact.png",
        task_status="[x]",
    )
    (tmp_path / "stale-root-artifact.png").unlink(missing_ok=True)
    _replace_task_field(
        feature / "tasks.md",
        "File(s)",
        "`tests/architecture/test_sdd_artifact_validator.py`, `stale-root-artifact.png`",
    )
    _write_valid_verification(feature / "verification.md", status="In Progress")

    issues = validate_sdd_root(tmp_path)

    invalid_issues = [issue for issue in issues if issue.code == "task-invalid-coordination-fields"]
    assert invalid_issues
    invalid_text = " ".join(issue.message for issue in invalid_issues)
    assert "file(s)" in invalid_text
    assert "touch set" in invalid_text
    assert "stale-root-artifact.png" in invalid_text


def test_tasks_allow_removed_file_records_outside_current_touch_surface(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-removed-file-record")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _write_valid_plan(feature / "plan.md", status="In Progress")
    _write_valid_tasks(
        feature / "tasks.md",
        status="In Progress",
        touch_set="tests/architecture/test_sdd_artifact_validator.py",
        task_status="[x]",
    )
    _insert_task_field(
        feature / "tasks.md",
        after_field="Touch set",
        field_name="Removed file(s)",
        value="`stale-root-artifact.png`",
    )
    _write_valid_verification(feature / "verification.md", status="In Progress")

    issues = validate_sdd_root(tmp_path)

    assert "task-invalid-coordination-fields" not in _issue_codes(issues)


def test_tasks_allow_current_glob_touch_paths_when_they_match(tmp_path: Path) -> None:
    skill_file = tmp_path / ".agents" / "skills" / "macro" / "SKILL.md"
    skill_file.parent.mkdir(parents=True)
    skill_file.write_text("# skill\n", encoding="utf-8")
    feature = _feature_dir(tmp_path, "active", "2026-06-09-current-glob-touch-path")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _write_valid_plan(feature / "plan.md", status="In Progress")
    _write_valid_tasks(
        feature / "tasks.md",
        status="In Progress",
        touch_set=".agents/skills/*/SKILL.md",
        task_status="[x]",
    )
    _write_valid_verification(feature / "verification.md", status="In Progress")

    issues = validate_sdd_root(tmp_path)

    assert "task-invalid-coordination-fields" not in _issue_codes(issues)


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


def test_tasks_reject_invalid_factory_lane_values(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-invalid-factory-lane")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _write_valid_plan(feature / "plan.md", status="In Progress")
    _write_valid_tasks(
        feature / "tasks.md",
        status="In Progress",
        factory_lane="Compatibility",
        task_status="[~]",
    )
    _write_valid_verification(feature / "verification.md", status="In Progress")

    issues = validate_sdd_root(tmp_path)

    invalid_issues = [issue for issue in issues if issue.code == "task-invalid-agent-loop-fields"]
    assert invalid_issues
    assert "factory lane" in " ".join(issue.message for issue in invalid_issues)


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


def test_delegated_tasks_validate_handoff_artifact_against_task(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-stale-subagent-handoff")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _write_valid_plan(feature / "plan.md", status="In Progress")
    report = tmp_path / "docs" / "generated" / "subagent-reports" / "valid.md"
    _write_valid_subagent_report(report)
    handoff = tmp_path / "docs" / "generated" / "subagent-handoffs" / "stale.md"
    handoff.parent.mkdir(parents=True)
    handoff.write_text(
        "\n".join(
            [
                "# Subagent Handoff - 2026-06-09-other-feature / Task 99",
                "",
                "Mode: write-allowed",
                "",
                "Context packet:",
                "",
                "```md",
                "# Context Packet - 2026-06-09-other-feature / Task 99",
                "```",
                "",
                "Report contract:",
                "- Parent validates the report with "
                "`uv run python scripts/validate_subagent_report.py --feature 2026-06-09-other-feature "
                "--task 99 --mode write-allowed --report <report.md>`.",
            ]
        ),
        encoding="utf-8",
    )
    _write_valid_tasks(
        feature / "tasks.md",
        status="In Progress",
        subagent_handoff="docs/generated/subagent-handoffs/stale.md",
        subagent_report="docs/generated/subagent-reports/valid.md",
        review_result="accepted",
        task_status="[~]",
    )
    _write_valid_verification(feature / "verification.md", status="In Progress")

    issues = validate_sdd_root(tmp_path)

    assert "task-invalid-subagent-handoff-artifact" in _issue_codes(issues)


def test_delegated_tasks_require_handoff_mode_constraints(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-handoff-mode-constraints")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _write_valid_plan(feature / "plan.md", status="In Progress")
    report = tmp_path / "docs" / "generated" / "subagent-reports" / "valid.md"
    report.parent.mkdir(parents=True)
    report.write_text(
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
                "## Required Reading Evidence",
                "- Task classification: Harness/tests",
                "- `AGENTS.md`",
                "- `docs/agent-playbook/task-reading-matrix.md`",
                "- `docs/WORKFLOW.md`",
                "- `docs/sdd/_templates/`",
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
    handoff = tmp_path / "docs" / "generated" / "subagent-handoffs" / "missing-mode-constraints.md"
    handoff.parent.mkdir(parents=True)
    handoff.write_text(
        "\n".join(
            [
                "# Subagent Handoff - 2026-06-09-handoff-mode-constraints / Task 1",
                "",
                "Mode: write-allowed",
                "",
                "Context packet:",
                "",
                "```md",
                "# Context Packet - 2026-06-09-handoff-mode-constraints / Task 1",
                "```",
                "",
                "Report contract:",
                "- Parent validates the report with "
                "`uv run python scripts/validate_subagent_report.py "
                "--feature 2026-06-09-handoff-mode-constraints "
                "--task 1 --mode write-allowed --report <report.md>`.",
            ]
        ),
        encoding="utf-8",
    )
    _write_valid_tasks(
        feature / "tasks.md",
        status="In Progress",
        subagent_handoff="docs/generated/subagent-handoffs/missing-mode-constraints.md",
        subagent_report="docs/generated/subagent-reports/valid.md",
        review_result="accepted",
        task_status="[~]",
    )
    _write_valid_verification(feature / "verification.md", status="In Progress")

    issues = validate_sdd_root(tmp_path)

    invalid_issues = [issue for issue in issues if issue.code == "task-invalid-subagent-handoff-artifact"]
    assert invalid_issues
    assert "missing Mode constraints" in " ".join(issue.message for issue in invalid_issues)


def test_delegated_tasks_require_embedded_context_packet_mode_constraints(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-embedded-context-mode-constraints")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _write_valid_plan(feature / "plan.md", status="In Progress")
    report = tmp_path / "docs" / "generated" / "subagent-reports" / "valid.md"
    report.parent.mkdir(parents=True)
    report.write_text(
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
                "## Required Reading Evidence",
                "- Task classification: Harness/tests",
                "- `AGENTS.md`",
                "- `docs/agent-playbook/task-reading-matrix.md`",
                "- `docs/WORKFLOW.md`",
                "- `docs/sdd/_templates/`",
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
    handoff = tmp_path / "docs" / "generated" / "subagent-handoffs" / "stale-context.md"
    handoff.parent.mkdir(parents=True)
    handoff.write_text(
        "\n".join(
            [
                "# Subagent Handoff - 2026-06-09-embedded-context-mode-constraints / Task 1",
                "",
                "Mode: write-allowed",
                "Mode constraints:",
                "- Write-allowed mode: changed files must stay inside Owned scope and avoid Do not touch.",
                "",
                "Context packet:",
                "",
                "```md",
                "# Context Packet - 2026-06-09-embedded-context-mode-constraints / Task 1",
                "",
                "Mode: write-allowed",
                "```",
                "",
                "Report contract:",
                "- Parent validates the report with "
                "`uv run python scripts/validate_subagent_report.py "
                "--feature 2026-06-09-embedded-context-mode-constraints "
                "--task 1 --mode write-allowed --report <report.md>`.",
            ]
        ),
        encoding="utf-8",
    )
    _write_valid_tasks(
        feature / "tasks.md",
        status="In Progress",
        subagent_handoff="docs/generated/subagent-handoffs/stale-context.md",
        subagent_report="docs/generated/subagent-reports/valid.md",
        review_result="accepted",
        task_status="[~]",
    )
    _write_valid_verification(feature / "verification.md", status="In Progress")

    issues = validate_sdd_root(tmp_path)

    invalid_issues = [issue for issue in issues if issue.code == "task-invalid-subagent-handoff-artifact"]
    assert invalid_issues
    assert "embedded Context Packet missing Mode constraints" in " ".join(
        issue.message for issue in invalid_issues
    )


def test_delegated_tasks_require_top_level_handoff_mode_constraints(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-top-level-handoff-mode-constraints")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _write_valid_plan(feature / "plan.md", status="In Progress")
    report = tmp_path / "docs" / "generated" / "subagent-reports" / "valid.md"
    report.parent.mkdir(parents=True)
    report.write_text(
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
                "## Required Reading Evidence",
                "- Task classification: Harness/tests",
                "- `AGENTS.md`",
                "- `docs/agent-playbook/task-reading-matrix.md`",
                "- `docs/WORKFLOW.md`",
                "- `docs/sdd/_templates/`",
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
    handoff = tmp_path / "docs" / "generated" / "subagent-handoffs" / "top-level-stale.md"
    handoff.parent.mkdir(parents=True)
    handoff.write_text(
        "\n".join(
            [
                "# Subagent Handoff - 2026-06-09-top-level-handoff-mode-constraints / Task 1",
                "",
                "Mode: write-allowed",
                "",
                "Context packet:",
                "",
                "```md",
                "# Context Packet - 2026-06-09-top-level-handoff-mode-constraints / Task 1",
                "",
                "Mode: write-allowed",
                "Mode constraints:",
                "- Write-allowed mode: changed files must stay inside Owned scope and avoid Do not touch.",
                "```",
                "",
                "Report contract:",
                "- Parent validates the report with "
                "`uv run python scripts/validate_subagent_report.py "
                "--feature 2026-06-09-top-level-handoff-mode-constraints "
                "--task 1 --mode write-allowed --report <report.md>`.",
            ]
        ),
        encoding="utf-8",
    )
    _write_valid_tasks(
        feature / "tasks.md",
        status="In Progress",
        subagent_handoff="docs/generated/subagent-handoffs/top-level-stale.md",
        subagent_report="docs/generated/subagent-reports/valid.md",
        review_result="accepted",
        task_status="[~]",
    )
    _write_valid_verification(feature / "verification.md", status="In Progress")

    issues = validate_sdd_root(tmp_path)

    invalid_issues = [issue for issue in issues if issue.code == "task-invalid-subagent-handoff-artifact"]
    assert invalid_issues
    assert "missing Mode constraints" in " ".join(issue.message for issue in invalid_issues)


def test_delegated_tasks_require_exact_report_validation_command(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-exact-report-validation-command")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _write_valid_plan(feature / "plan.md", status="In Progress")
    report = tmp_path / "docs" / "generated" / "subagent-reports" / "valid.md"
    report.parent.mkdir(parents=True)
    report.write_text(
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
                "## Required Reading Evidence",
                "- Task classification: Harness/tests",
                "- `AGENTS.md`",
                "- `docs/agent-playbook/task-reading-matrix.md`",
                "- `docs/WORKFLOW.md`",
                "- `docs/sdd/_templates/`",
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
    handoff = tmp_path / "docs" / "generated" / "subagent-handoffs" / "token-only-command.md"
    handoff.parent.mkdir(parents=True)
    handoff.write_text(
        "\n".join(
            [
                "# Subagent Handoff - 2026-06-09-exact-report-validation-command / Task 1",
                "",
                "Mode: write-allowed",
                "Mode constraints:",
                "- Write-allowed mode: changed files must stay inside Owned scope and avoid Do not touch.",
                "",
                "Context packet:",
                "",
                "```md",
                "# Context Packet - 2026-06-09-exact-report-validation-command / Task 1",
                "",
                "Mode: write-allowed",
                "Mode constraints:",
                "- Write-allowed mode: changed files must stay inside Owned scope and avoid Do not touch.",
                "```",
                "",
                "Report contract:",
                "- Validation token inventory: scripts/validate_subagent_report.py, --feature, "
                "2026-06-09-exact-report-validation-command, --task, 1, --mode, "
                "write-allowed, --report.",
            ]
        ),
        encoding="utf-8",
    )
    _write_valid_tasks(
        feature / "tasks.md",
        status="In Progress",
        subagent_handoff="docs/generated/subagent-handoffs/token-only-command.md",
        subagent_report="docs/generated/subagent-reports/valid.md",
        review_result="accepted",
        task_status="[~]",
    )
    _write_valid_verification(feature / "verification.md", status="In Progress")

    issues = validate_sdd_root(tmp_path)

    invalid_issues = [issue for issue in issues if issue.code == "task-invalid-subagent-handoff-artifact"]
    assert invalid_issues
    assert "report validation command must be exact" in " ".join(
        issue.message for issue in invalid_issues
    )


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


def test_delegated_report_mode_must_match_handoff_mode(tmp_path: Path) -> None:
    feature = _feature_dir(tmp_path, "active", "2026-06-09-report-mode-drift")
    _write_valid_spec(feature / "spec.md", status="In Progress")
    _write_valid_plan(feature / "plan.md", status="In Progress")
    handoff = tmp_path / "docs" / "generated" / "subagent-handoffs" / "valid.md"
    _write_valid_subagent_handoff(handoff, feature_slug="2026-06-09-report-mode-drift", mode="read-only")
    report = tmp_path / "docs" / "generated" / "subagent-reports" / "mode-drift.md"
    _write_valid_subagent_report(report)
    _write_valid_tasks(
        feature / "tasks.md",
        status="In Progress",
        subagent_handoff="docs/generated/subagent-handoffs/valid.md",
        subagent_report="docs/generated/subagent-reports/mode-drift.md",
        review_result="accepted",
        task_status="[~]",
    )
    _write_valid_verification(feature / "verification.md", status="In Progress")

    issues = validate_sdd_root(tmp_path)

    assert "task-invalid-subagent-report-artifact" in _issue_codes(issues)
    assert "report mode must match handoff mode: read-only" in " ".join(issue.message for issue in issues)


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


def test_active_touch_sets_reject_nested_or_misdirected_coordination(tmp_path: Path) -> None:
    parent_touch = _feature_dir(tmp_path, "active", "2026-06-09-parent-touch")
    child_touch = _feature_dir(tmp_path, "active", "2026-06-09-child-touch")
    fixtures = (
        (
            parent_touch,
            "docs/agent-playbook",
            "coordinate with 2026-06-09-unrelated for unrelated generated index work.",
        ),
        (
            child_touch,
            "docs/agent-playbook/context-packet-template.md",
            "coordinate with 2026-06-09-unrelated for unrelated generated index work.",
        ),
    )
    for feature, touch_set, conflict_set in fixtures:
        _write_valid_spec(feature / "spec.md", status="In Progress")
        _write_valid_plan(feature / "plan.md", status="In Progress")
        _write_valid_tasks(
            feature / "tasks.md",
            status="In Progress",
            touch_set=touch_set,
            conflict_set=conflict_set,
        )
        _write_valid_verification(feature / "verification.md", status="In Progress")

    issues = validate_sdd_root(tmp_path)

    assert "active-touch-conflict" in _issue_codes(issues)
    messages = "\n".join(issue.message for issue in issues if issue.code == "active-touch-conflict")
    assert "docs/agent-playbook" in messages
    assert "2026-06-09-child-touch" in messages
    assert "2026-06-09-parent-touch" in messages


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
    feature_dir = _feature_relative_dir(path)
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
                "## Background",
                "",
                f"The fixture spec is grounded by its own source record (`{feature_dir}/spec.md:1`).",
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
def _task_fixture_paths(values: tuple[str, ...]) -> tuple[str, ...]:
    paths: list[str] = []
    for value in values:
        for item in re.split(r"[,;]", value.replace("`", "")):
            candidate = item.strip()
            if not candidate or candidate.lower() in {"none", "not delegated"}:
                continue
            paths.append(candidate)
    return tuple(dict.fromkeys(paths))


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
                "| Spec maps to tasks. | Pass: spec maps to tasks. |",
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
    factory_lane: str = "Harness/tests",
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
                "| Implement | Tasks below are TDD ordered. |",
                "| Verify | `verification.md` captures command output. |",
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
                f"- **Factory lane**: {factory_lane}",
                "- **Deterministic constraints**: SDD validator, generated index, make check-all.",
                "- **On-demand context**: `docs/WORKFLOW.md`, `docs/sdd/_templates/`.",
                "- **Kill/defer criteria**: Stop if validator cannot prove artifact truth.",
                "- **Eval/repair signal**: Record harness failures and review defects.",
                f"- **Status**: {task_status}",
            ]
        ),
        encoding="utf-8",
    )
    for repo_path in _task_fixture_paths(
        (
            "tests/architecture/test_sdd_artifact_validator.py",
            "scripts/validate_sdd_artifacts.py",
            touch_set,
        )
    ):
        if any(character in repo_path for character in "*?[]"):
            continue
        target = path.parents[5] / repo_path
        if target.suffix:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.touch(exist_ok=True)
            continue
        target.mkdir(parents=True, exist_ok=True)


def _split_only_task_block(path: Path) -> tuple[str, str]:
    text = path.read_text(encoding="utf-8")
    prefix, task_body = text.split("### Task 1 - Valid", 1)
    return prefix, "### Task 1 - Valid" + task_body


def _move_only_task_into_fenced_block(path: Path) -> None:
    prefix, task_block = _split_only_task_block(path)
    path.write_text(prefix + "```md\n" + task_block.rstrip() + "\n```\n", encoding="utf-8")


def _move_only_task_after_tasks_section(path: Path) -> None:
    prefix, task_block = _split_only_task_block(path)
    path.write_text(
        prefix + "_No task records here._\n\n## Appendix\n\n" + task_block,
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


def _write_valid_subagent_handoff(
    path: Path,
    *,
    feature_slug: str,
    task_number: int = 1,
    mode: str = "write-allowed",
) -> None:
    path.parent.mkdir(parents=True)
    task_anchor = f"Task {task_number}"
    path.write_text(
        "\n".join(
            [
                f"# Subagent Handoff - {feature_slug} / {task_anchor}",
                "",
                f"Mode: {mode}",
                "Mode constraints:",
                *mode_constraint_lines(mode),
                "",
                "Context packet:",
                "",
                "```md",
                f"# Context Packet - {feature_slug} / {task_anchor}",
                "",
                f"Mode: {mode}",
                "Mode constraints:",
                *mode_constraint_lines(mode),
                "```",
                "",
                "Report contract:",
                "- Parent validates the report with "
                f"`uv run python scripts/validate_subagent_report.py --feature {feature_slug} "
                f"--task {task_number} --mode {mode} --report <report.md>`.",
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
    _replace_metadata_field(path, field_name, f"`{value}`")


def _replace_metadata_field(path: Path, field_name: str, value: str) -> None:
    needle = f"**{field_name}**:"
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(needle):
            lines.append(f"**{field_name}**: {value}")
        else:
            lines.append(line)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _replace_task_field(path: Path, field_name: str, value: str) -> None:
    needle = f"- **{field_name}**:"
    lines = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(needle):
            lines.append(f"- **{field_name}**: {value}")
        else:
            lines.append(line)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _insert_task_field(path: Path, *, after_field: str, field_name: str, value: str) -> None:
    needle = f"- **{after_field}**:"
    lines = []
    inserted = False
    for line in path.read_text(encoding="utf-8").splitlines():
        lines.append(line)
        if not inserted and line.startswith(needle):
            lines.append(f"- **{field_name}**: {value}")
            inserted = True
    if not inserted:
        raise AssertionError(f"task field not found: {after_field}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _replace_section_body(path: Path, heading: str, body_lines: tuple[str, ...]) -> None:
    text = path.read_text(encoding="utf-8")
    prefix, section_and_rest = text.split(heading, 1)
    _section_body, separator, rest = section_and_rest.partition("\n## ")
    replacement = "\n" + "\n".join(body_lines) + "\n"
    if separator:
        path.write_text(prefix + heading + replacement + separator + rest, encoding="utf-8")
        return
    path.write_text(prefix + heading + replacement, encoding="utf-8")


def _insert_plan_preflight_line(path: Path, line: str) -> None:
    text = path.read_text(encoding="utf-8")
    prefix, rest = text.split("## Analyze Gate", 1)
    preflight = "\n## Pre-flight\n\n" + line + "\n\n"
    path.write_text(prefix + preflight + "## Analyze Gate" + rest, encoding="utf-8")


def _append_acceptance_criterion(path: Path, number: int) -> None:
    path.write_text(
        path.read_text(encoding="utf-8")
        + f"\n- AC{number}. WHEN another behavior exists THEN the harness SHALL map it to a command.\n",
        encoding="utf-8",
    )


def _replace_acceptance_criterion(path: Path, number: int, replacement: str) -> None:
    target = f"- AC{number}."
    lines = []
    replaced = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(target):
            lines.append(f"- {replacement}")
            replaced = True
        else:
            lines.append(line)
    if not replaced:
        raise AssertionError(f"missing AC{number} criterion in {path}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _append_acceptance_command(path: Path, number: int) -> None:
    path.write_text(
        path.read_text(encoding="utf-8")
        + f"\n- AC{number}: `uv run pytest tests/architecture/test_sdd_artifact_validator.py -q`\n",
        encoding="utf-8",
    )


def _replace_acceptance_command(path: Path, number: int, command: str) -> None:
    _replace_acceptance_command_line(path, number, f"- AC{number}: `{command}`")


def _replace_acceptance_command_line(path: Path, number: int, replacement: str) -> None:
    target = f"- AC{number}:"
    lines = []
    replaced = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith(target):
            lines.append(replacement)
            replaced = True
        else:
            lines.append(line)
    if not replaced:
        raise AssertionError(f"missing AC{number} command in {path}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _replace_spec_compliance_row(path: Path, replacement: str) -> None:
    lines = []
    replaced = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("| AC1 |"):
            lines.append(replacement)
            replaced = True
        else:
            lines.append(line)
    if not replaced:
        raise AssertionError(f"missing AC1 compliance row in {path}")
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
