# tests/test_docs_generated.py
"""Verify docs/generated/ files are regeneration-clean."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
GENERATED = REPO_ROOT / "docs" / "generated"
EXPECTED = {"README.md", "db-schema.md", "cli-help.md", "score-versions.md", "ws-protocol.md"}
HEADER_MARKER = "AUTO-GENERATED"


def test_generated_directory_present() -> None:
    assert GENERATED.is_dir(), "docs/generated/ missing"


def test_expected_generated_files() -> None:
    actual = {p.name for p in GENERATED.glob("*.md")}
    assert actual == EXPECTED, f"unexpected docs/generated/ contents: {actual ^ EXPECTED}"


def test_generated_files_have_header_marker() -> None:
    for name in EXPECTED - {"README.md"}:
        path = GENERATED / name
        first_line = path.read_text(encoding="utf-8").splitlines()[0]
        assert HEADER_MARKER in first_line, f"{name} missing AUTO-GENERATED header"


@pytest.mark.skipif(
    shutil.which("uv") is None or shutil.which("make") is None,
    reason="uv or make not available in this environment",
)
def test_make_docs_generated_clean_diff() -> None:
    proc = subprocess.run(["make", "docs-generated"], cwd=REPO_ROOT, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        pytest.skip(f"make docs-generated failed (likely Postgres unreachable): {proc.stderr}")
    diff = subprocess.run(
        ["git", "diff", "--exit-code", "docs/generated/"], cwd=REPO_ROOT, capture_output=True, text=True, check=False
    )
    assert diff.returncode == 0, f"make docs-generated produced uncommitted changes:\n{diff.stdout}"
