# tests/architecture/test_completion_gates.py
"""Architecture test: completion-gate documents must reference the canonical command.

Catches the failure mode where someone updates docs/TESTING.md but not WORKFLOW.md
(or vice versa), or the verification template loses one of its required sections.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
TESTING = ROOT / "docs" / "TESTING.md"
WORKFLOW = ROOT / "docs" / "WORKFLOW.md"
TEMPLATE = ROOT / "docs" / "superpowers" / "_templates" / "verification-template.md"


@pytest.mark.architecture
def test_testing_md_references_make_check_all() -> None:
    text = TESTING.read_text(encoding="utf-8")
    assert "make check-all" in text, (
        "docs/TESTING.md must reference `make check-all` as the canonical completion-verification entry."
    )


@pytest.mark.architecture
def test_workflow_md_references_make_check_all() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "make check-all" in text, "docs/WORKFLOW.md must reference `make check-all` in its completion-gates section."


@pytest.mark.architecture
def test_verification_template_has_three_required_sections() -> None:
    text = TEMPLATE.read_text(encoding="utf-8")
    for required in ("## Coverage", "## Skipped tests", "## E2E golden path"):
        assert required in text, (
            f"verification-template.md is missing required section `{required}`. "
            "Did docs/TESTING.md / WORKFLOW.md change without the template being updated?"
        )


@pytest.mark.architecture
def test_old_three_command_recipe_not_in_workflow() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    forbidden = "uv run ruff check ., uv run pytest, uv run python -m compileall"
    assert forbidden not in text, (
        "Old three-command recipe should be replaced with `make check-all`; found legacy phrase in docs/WORKFLOW.md."
    )
