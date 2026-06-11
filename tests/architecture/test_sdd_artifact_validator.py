from __future__ import annotations

import re
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
                "",
                "Context packet:",
                "",
                "```md",
                f"# Context Packet - {feature_slug} / {task_anchor}",
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
