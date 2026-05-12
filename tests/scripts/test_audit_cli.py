from __future__ import annotations

import subprocess
import sys


def test_help_runs() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/audit_duplicate_tokens.py", "--help"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "--dry-run" in result.stdout
    assert "--apply" in result.stdout
    assert "--report" in result.stdout
    assert "--chain" in result.stdout
    assert "--symbol" in result.stdout
    assert "--threshold-holders" in result.stdout
    assert "--threshold-liq-usd" in result.stdout
    assert "--no-external" in result.stdout
    assert "--only-phase1" in result.stdout
    assert "--only-phase2" in result.stdout


def test_requires_dry_run_or_apply() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/audit_duplicate_tokens.py"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "--dry-run" in result.stderr or "--apply" in result.stderr
