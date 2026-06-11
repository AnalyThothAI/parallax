from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

import pytest

from scripts.regen_sdd_work_index import render_index
from scripts.validate_sdd_artifacts import (
    KNOWN_ISSUE_CODES,
    ArtifactRecord,
    SddFeature,
    TaskRecord,
    scan_sdd_features,
    validate_sdd_root,
)

ROOT = Path(__file__).resolve().parents[2]
PLAYBOOK = ROOT / "docs" / "agent-playbook"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


@pytest.mark.architecture
def test_agent_playbook_reading_matrix_covers_core_incident_types() -> None:
    text = _read(PLAYBOOK / "task-reading-matrix.md")
    required_sections = (
        "## Real Data And Provider Debugging",
        "## Token Radar Or Public Row Gaps",
        "## Worker Backlog Or Stuck Worker",
        "## Product LLM Agent Run",
        "## Frontend CSS Or Route Shell",
        "## Macro Freshness Or Regime Readiness",
    )
    for section in required_sections:
        assert section in text

    for required_phrase in (
        "Required reading:",
        "Diagnostic commands:",
        "Answer must separate:",
        "Never print secrets",
        "PostgreSQL facts",
        "read models",
        "control plane",
    ):
        assert required_phrase in text


@pytest.mark.architecture
def test_agent_playbook_has_task_examples_and_read_model_checklist() -> None:
    examples = _read(PLAYBOOK / "task-examples.md")
    checklist = _read(PLAYBOOK / "read-model-change-checklist.md")
    matrix = _read(PLAYBOOK / "task-reading-matrix.md")

    for required_phrase in (
        "## Real Data Provider Diagnostic",
        "## Worker Backlog",
        "## Frontend Route Shell QA",
        "## Read Model Change Review",
        "Goal:",
        "Done when:",
        "Required reading",
        "Verification",
    ):
        assert required_phrase in examples

    for required_phrase in (
        "stable product/window keys",
        "single runtime writer",
        "unchanged projections write zero serving rows",
        "bounded `interval_seconds` catch-up",
        "Provider raw frames are inputs, not facts",
    ):
        assert required_phrase in checklist

    assert "docs/agent-playbook/task-examples.md" in matrix
    assert "docs/agent-playbook/read-model-change-checklist.md" in matrix


@pytest.mark.architecture
def test_repo_scoped_agent_skills_cover_high_frequency_workflows() -> None:
    skills_root = ROOT / ".agents" / "skills"
    expected_skills = {
        "parallax-worker-debugging": (
            "Worker Backlog Or Stuck Worker",
            "docs/WORKER_FLOW.md",
            "uv run parallax ops worker-status --help",
        ),
        "parallax-real-data-provider-diagnostics": (
            "Real Data And Provider Debugging",
            "uv run parallax config",
            "Never print secrets",
        ),
        "parallax-frontend-verification": (
            "Frontend CSS Or Route Shell",
            "docs/FRONTEND.md",
            "cd web && npm run lint",
        ),
        "parallax-read-model-review": (
            "Read Model Change Review",
            "docs/agent-playbook/read-model-change-checklist.md",
            "single runtime writer",
        ),
    }

    for skill_name, required_phrases in expected_skills.items():
        skill_file = skills_root / skill_name / "SKILL.md"
        assert skill_file.exists(), f"{skill_file.relative_to(ROOT)} missing"
        text = _read(skill_file)
        assert f"name: {skill_name}" in text
        assert "description:" in text
        for phrase in required_phrases:
            assert phrase in text


@pytest.mark.architecture
def test_subagent_handoff_templates_define_context_and_conflict_contracts() -> None:
    handoff = _read(PLAYBOOK / "subagent-handoff-template.md")
    context = _read(PLAYBOOK / "context-packet-template.md")

    for required_phrase in (
        "Mode",
        "Owned scope",
        "Must read",
        "Do not touch",
        "Report contract",
        "Required Reading Evidence",
        "validate_subagent_report.py",
        "Expected output",
        "Conflict set",
        "Verification evidence",
    ):
        assert required_phrase in handoff

    for required_phrase in (
        "Truth boundary",
        "Facts",
        "Read models",
        "Control plane",
        "Unknowns",
        "Redactions",
    ):
        assert required_phrase in context


@pytest.mark.architecture
def test_development_agent_factory_model_is_explicit_and_bounded() -> None:
    text = _read(PLAYBOOK / "factory-operating-model.md")
    for required_phrase in (
        "## Deterministic Constraints",
        "## On-Demand Context",
        "## Lane Budget",
        "maximum of six active lanes",
        "Parent integrator",
        "Kill / Defer Criteria",
        "Product LLM agents are not development-agent lanes",
        "Subagent output is evidence, not authority",
        "scripts/build_agent_context_packet.py",
        "scripts/dispatch_sdd_task.py",
        "scripts/validate_subagent_report.py",
    ):
        assert required_phrase in text


@pytest.mark.architecture
def test_context_packet_cli(tmp_path: Path) -> None:
    script = ROOT / "scripts" / "build_agent_context_packet.py"
    assert script.exists()
    _write_context_packet_fixture(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--root",
            str(tmp_path),
            "--feature",
            "2026-06-09-context-packet-fixture",
            "--task",
            "1",
            "--mode",
            "read-only",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    for required_phrase in (
        "# Context Packet - 2026-06-09-context-packet-fixture / Task 1",
        "Mode: read-only",
        "Factory lane: Harness/tests",
        "Owned scope:",
        "Do not touch:",
        "coordinate with 2026-06-09-other-feature for context packet generator, docs, and tests.",
        "Deterministic constraints:",
        "On-demand context:",
        "Kill/defer criteria:",
        "Eval/repair signal:",
        "Verification evidence:",
        "Redactions:",
        "Product LLM agents are not development-agent lanes",
    ):
        assert required_phrase in result.stdout

    for forbidden_phrase in ("<task", "<path>", "<pending>", "~/.parallax/", "token=", "cookie=", "dsn="):
        assert forbidden_phrase not in result.stdout.lower()


@pytest.mark.architecture
def test_sdd_task_dispatch_cli_emits_handoff_for_in_progress_task(tmp_path: Path) -> None:
    script = ROOT / "scripts" / "dispatch_sdd_task.py"
    assert script.exists()
    _write_context_packet_fixture(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--root",
            str(tmp_path),
            "--feature",
            "2026-06-09-context-packet-fixture",
            "--task",
            "1",
            "--mode",
            "read-only",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    for required_phrase in (
        "# Subagent Handoff - 2026-06-09-context-packet-fixture / Task 1",
        "Mode: read-only",
        "Goal:",
        "Owned scope:",
        "Do not touch:",
        "Context packet:",
        "Report contract:",
        "scripts/validate_subagent_report.py",
        "--feature 2026-06-09-context-packet-fixture",
        "--task 1",
        "# Context Packet - 2026-06-09-context-packet-fixture / Task 1",
        "Verification evidence:",
    ):
        assert required_phrase in result.stdout


@pytest.mark.architecture
def test_sdd_task_dispatch_cli_refuses_completed_task(tmp_path: Path) -> None:
    script = ROOT / "scripts" / "dispatch_sdd_task.py"
    assert script.exists()
    _write_context_packet_fixture(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--root",
            str(tmp_path),
            "--feature",
            "2026-06-09-context-packet-fixture",
            "--task",
            "2",
            "--mode",
            "read-only",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "already complete" in result.stderr


@pytest.mark.architecture
def test_sdd_task_dispatch_cli_refuses_unmet_dependencies(tmp_path: Path) -> None:
    script = ROOT / "scripts" / "dispatch_sdd_task.py"
    assert script.exists()
    _write_context_packet_fixture(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--root",
            str(tmp_path),
            "--feature",
            "2026-06-09-context-packet-fixture",
            "--task",
            "3",
            "--mode",
            "read-only",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "dependencies are not complete" in result.stderr


@pytest.mark.architecture
def test_sdd_gate_check_cli_accepts_individual_gates(tmp_path: Path) -> None:
    script = ROOT / "scripts" / "check_sdd_gate.py"
    assert script.exists()
    _write_context_packet_fixture(tmp_path)
    _create_context_packet_fixture_paths(tmp_path)

    for gate in ("clarify", "checklist", "analyze", "implement"):
        result = subprocess.run(
            [
                sys.executable,
                str(script),
                "--root",
                str(tmp_path),
                "--feature",
                "2026-06-09-context-packet-fixture",
                "--gate",
                gate,
                "--check",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )

        assert result.returncode == 0, gate + "\n" + result.stdout + result.stderr
        assert f"{gate} gate passed" in result.stdout


@pytest.mark.architecture
def test_sdd_gate_check_cli_rejects_failed_analyze_gate(tmp_path: Path) -> None:
    script = ROOT / "scripts" / "check_sdd_gate.py"
    assert script.exists()
    _write_context_packet_fixture(tmp_path)
    _create_context_packet_fixture_paths(tmp_path)
    plan_path = (
        tmp_path
        / "docs"
        / "sdd"
        / "features"
        / "active"
        / "2026-06-09-context-packet-fixture"
        / "plan.md"
    )
    plan_text = plan_path.read_text(encoding="utf-8")
    plan_path.write_text(plan_text.replace("Pass: fixture", "Fail: fixture"), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--root",
            str(tmp_path),
            "--feature",
            "2026-06-09-context-packet-fixture",
            "--gate",
            "analyze",
            "--check",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "plan-analyze-gate-invalid" in result.stderr


@pytest.mark.architecture
def test_sdd_gate_check_cli_rejects_unbounded_analyze_status(tmp_path: Path) -> None:
    script = ROOT / "scripts" / "check_sdd_gate.py"
    assert script.exists()
    _write_context_packet_fixture(tmp_path)
    _create_context_packet_fixture_paths(tmp_path)
    plan_path = (
        tmp_path
        / "docs"
        / "sdd"
        / "features"
        / "active"
        / "2026-06-09-context-packet-fixture"
        / "plan.md"
    )
    plan_text = plan_path.read_text(encoding="utf-8")
    plan_path.write_text(plan_text.replace("Pass: fixture", "Warn: fixture"), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--root",
            str(tmp_path),
            "--feature",
            "2026-06-09-context-packet-fixture",
            "--gate",
            "analyze",
            "--check",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "plan-analyze-gate-invalid" in result.stderr


@pytest.mark.architecture
def test_sdd_gate_check_cli_rejects_analyze_status_without_evidence(tmp_path: Path) -> None:
    script = ROOT / "scripts" / "check_sdd_gate.py"
    assert script.exists()
    _write_context_packet_fixture(tmp_path)
    _create_context_packet_fixture_paths(tmp_path)
    plan_path = (
        tmp_path
        / "docs"
        / "sdd"
        / "features"
        / "active"
        / "2026-06-09-context-packet-fixture"
        / "plan.md"
    )
    plan_text = plan_path.read_text(encoding="utf-8")
    plan_path.write_text(
        plan_text.replace("Pass: fixture only exercises development-agent harness.", "Pass:"),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--root",
            str(tmp_path),
            "--feature",
            "2026-06-09-context-packet-fixture",
            "--gate",
            "analyze",
            "--check",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "plan-analyze-gate-invalid" in result.stderr


@pytest.mark.architecture
def test_sdd_gate_check_cli_ignores_non_canonical_analyze_tables(tmp_path: Path) -> None:
    script = ROOT / "scripts" / "check_sdd_gate.py"
    assert script.exists()
    _write_context_packet_fixture(tmp_path)
    _create_context_packet_fixture_paths(tmp_path)
    plan_path = (
        tmp_path
        / "docs"
        / "sdd"
        / "features"
        / "active"
        / "2026-06-09-context-packet-fixture"
        / "plan.md"
    )
    plan_text = plan_path.read_text(encoding="utf-8")
    plan_path.write_text(
        plan_text.replace(
            "## Acceptance test commands",
            "\n| Note | Value |\n"
            "|------|-------|\n"
            "| Non-gate example | This table is context, not an Analyze Gate result. |\n\n"
            "## Acceptance test commands",
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--root",
            str(tmp_path),
            "--feature",
            "2026-06-09-context-packet-fixture",
            "--gate",
            "analyze",
            "--check",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "analyze gate passed" in result.stdout


@pytest.mark.architecture
def test_sdd_gate_check_cli_rejects_invalid_analyze_result_with_placeholder_check(tmp_path: Path) -> None:
    script = ROOT / "scripts" / "check_sdd_gate.py"
    assert script.exists()
    _write_context_packet_fixture(tmp_path)
    _create_context_packet_fixture_paths(tmp_path)
    plan_path = (
        tmp_path
        / "docs"
        / "sdd"
        / "features"
        / "active"
        / "2026-06-09-context-packet-fixture"
        / "plan.md"
    )
    plan_text = plan_path.read_text(encoding="utf-8")
    plan_path.write_text(
        plan_text.replace(
            "| Product runtime untouched. | Pass: fixture only exercises development-agent harness. |",
            "| Product runtime untouched. | Pass: fixture only exercises development-agent harness. |\n"
            "| <pending> | Warn: placeholder checks cannot hide invalid Analyze results. |",
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--root",
            str(tmp_path),
            "--feature",
            "2026-06-09-context-packet-fixture",
            "--gate",
            "analyze",
            "--check",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "plan-analyze-gate-invalid" in result.stderr


@pytest.mark.architecture
def test_sdd_gate_check_cli_rejects_header_only_gate_tables(tmp_path: Path) -> None:
    script = ROOT / "scripts" / "check_sdd_gate.py"
    assert script.exists()
    _write_context_packet_fixture(tmp_path)
    spec_path = (
        tmp_path
        / "docs"
        / "sdd"
        / "features"
        / "active"
        / "2026-06-09-context-packet-fixture"
        / "spec.md"
    )
    spec_text = spec_path.read_text(encoding="utf-8")
    before, clarifications_and_rest = spec_text.split("## Clarifications", 1)
    _old_clarifications, after_clarifications = clarifications_and_rest.split("## Requirement Checklist", 1)
    spec_path.write_text(
        before
        + "## Clarifications\n\n"
        + "| Question | Answer | Approved by | Approved at |\n"
        + "|----------|--------|-------------|-------------|\n\n"
        + "## Requirement Checklist"
        + after_clarifications,
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--root",
            str(tmp_path),
            "--feature",
            "2026-06-09-context-packet-fixture",
            "--gate",
            "clarify",
            "--check",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "gate-evidence-missing" in result.stderr


@pytest.mark.architecture
def test_sdd_gate_check_cli_rejects_single_cell_gate_rows(tmp_path: Path) -> None:
    script = ROOT / "scripts" / "check_sdd_gate.py"
    assert script.exists()
    _write_context_packet_fixture(tmp_path)
    spec_path = (
        tmp_path
        / "docs"
        / "sdd"
        / "features"
        / "active"
        / "2026-06-09-context-packet-fixture"
        / "spec.md"
    )
    spec_text = spec_path.read_text(encoding="utf-8")
    before, clarifications_and_rest = spec_text.split("## Clarifications", 1)
    _old_clarifications, after_clarifications = clarifications_and_rest.split("## Requirement Checklist", 1)
    spec_path.write_text(
        before
        + "## Clarifications\n\n"
        + "| Question | Answer | Approved by | Approved at |\n"
        + "|----------|\n"
        + "| Decided by qinghuan on 2026-06-09 |\n\n"
        + "## Requirement Checklist"
        + after_clarifications,
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--root",
            str(tmp_path),
            "--feature",
            "2026-06-09-context-packet-fixture",
            "--gate",
            "clarify",
            "--check",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "gate-evidence-missing" in result.stderr


@pytest.mark.architecture
def test_sdd_gate_check_cli_rejects_gate_tables_without_separator_rows(tmp_path: Path) -> None:
    script = ROOT / "scripts" / "check_sdd_gate.py"
    assert script.exists()
    _write_context_packet_fixture(tmp_path)
    spec_path = (
        tmp_path
        / "docs"
        / "sdd"
        / "features"
        / "active"
        / "2026-06-09-context-packet-fixture"
        / "spec.md"
    )
    spec_text = spec_path.read_text(encoding="utf-8")
    before, clarifications_and_rest = spec_text.split("## Clarifications", 1)
    _old_clarifications, after_clarifications = clarifications_and_rest.split("## Requirement Checklist", 1)
    spec_path.write_text(
        before
        + "## Clarifications\n\n"
        + "| Question | Answer | Approved by | Approved at |\n"
        + "| Should malformed tables pass? | No. | qinghuan | 2026-06-09 |\n\n"
        + "## Requirement Checklist"
        + after_clarifications,
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--root",
            str(tmp_path),
            "--feature",
            "2026-06-09-context-packet-fixture",
            "--gate",
            "clarify",
            "--check",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "gate-evidence-missing" in result.stderr


@pytest.mark.architecture
def test_sdd_gate_check_cli_rejects_body_rows_before_separator(tmp_path: Path) -> None:
    script = ROOT / "scripts" / "check_sdd_gate.py"
    assert script.exists()
    _write_context_packet_fixture(tmp_path)
    spec_path = (
        tmp_path
        / "docs"
        / "sdd"
        / "features"
        / "active"
        / "2026-06-09-context-packet-fixture"
        / "spec.md"
    )
    spec_text = spec_path.read_text(encoding="utf-8")
    before, clarifications_and_rest = spec_text.split("## Clarifications", 1)
    _old_clarifications, after_clarifications = clarifications_and_rest.split("## Requirement Checklist", 1)
    spec_path.write_text(
        before
        + "## Clarifications\n\n"
        + "| Question | Answer | Approved by | Approved at |\n"
        + "| Should malformed tables pass? | No. | qinghuan | 2026-06-09 |\n"
        + "|----------|--------|-------------|-------------|\n\n"
        + "## Requirement Checklist"
        + after_clarifications,
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--root",
            str(tmp_path),
            "--feature",
            "2026-06-09-context-packet-fixture",
            "--gate",
            "clarify",
            "--check",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "gate-evidence-missing" in result.stderr


@pytest.mark.architecture
def test_sdd_gate_check_cli_rejects_empty_separator_rows(tmp_path: Path) -> None:
    script = ROOT / "scripts" / "check_sdd_gate.py"
    assert script.exists()
    _write_context_packet_fixture(tmp_path)
    spec_path = (
        tmp_path
        / "docs"
        / "sdd"
        / "features"
        / "active"
        / "2026-06-09-context-packet-fixture"
        / "spec.md"
    )
    spec_text = spec_path.read_text(encoding="utf-8")
    before, clarifications_and_rest = spec_text.split("## Clarifications", 1)
    _old_clarifications, after_clarifications = clarifications_and_rest.split("## Requirement Checklist", 1)
    spec_path.write_text(
        before
        + "## Clarifications\n\n"
        + "| Question | Answer | Approved by | Approved at |\n"
        + "| | | | |\n"
        + "| Should malformed tables pass? | No. | qinghuan | 2026-06-09 |\n\n"
        + "## Requirement Checklist"
        + after_clarifications,
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--root",
            str(tmp_path),
            "--feature",
            "2026-06-09-context-packet-fixture",
            "--gate",
            "clarify",
            "--check",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "gate-evidence-missing" in result.stderr


@pytest.mark.architecture
def test_sdd_gate_check_cli_rejects_repeated_separator_rows(tmp_path: Path) -> None:
    script = ROOT / "scripts" / "check_sdd_gate.py"
    assert script.exists()
    _write_context_packet_fixture(tmp_path)
    spec_path = (
        tmp_path
        / "docs"
        / "sdd"
        / "features"
        / "active"
        / "2026-06-09-context-packet-fixture"
        / "spec.md"
    )
    spec_text = spec_path.read_text(encoding="utf-8")
    before, clarifications_and_rest = spec_text.split("## Clarifications", 1)
    _old_clarifications, after_clarifications = clarifications_and_rest.split("## Requirement Checklist", 1)
    spec_path.write_text(
        before
        + "## Clarifications\n\n"
        + "| Question | Answer | Approved by | Approved at |\n"
        + "|----------|--------|-------------|-------------|\n"
        + "|----------|--------|-------------|-------------|\n"
        + "| Should malformed tables pass? | No. | qinghuan | 2026-06-09 |\n\n"
        + "## Requirement Checklist"
        + after_clarifications,
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--root",
            str(tmp_path),
            "--feature",
            "2026-06-09-context-packet-fixture",
            "--gate",
            "clarify",
            "--check",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "gate-evidence-missing" in result.stderr


@pytest.mark.architecture
def test_sdd_gate_check_cli_rejects_repeated_header_rows(tmp_path: Path) -> None:
    script = ROOT / "scripts" / "check_sdd_gate.py"
    assert script.exists()
    _write_context_packet_fixture(tmp_path)
    spec_path = (
        tmp_path
        / "docs"
        / "sdd"
        / "features"
        / "active"
        / "2026-06-09-context-packet-fixture"
        / "spec.md"
    )
    spec_text = spec_path.read_text(encoding="utf-8")
    before, clarifications_and_rest = spec_text.split("## Clarifications", 1)
    _old_clarifications, after_clarifications = clarifications_and_rest.split("## Requirement Checklist", 1)
    spec_path.write_text(
        before
        + "## Clarifications\n\n"
        + "| Question | Answer | Approved by | Approved at |\n"
        + "|----------|--------|-------------|-------------|\n"
        + "| Question | Answer | Approved by | Approved at |\n\n"
        + "## Requirement Checklist"
        + after_clarifications,
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--root",
            str(tmp_path),
            "--feature",
            "2026-06-09-context-packet-fixture",
            "--gate",
            "clarify",
            "--check",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "gate-evidence-missing" in result.stderr


@pytest.mark.architecture
def test_sdd_gate_check_cli_rejects_unclosed_table_rows(tmp_path: Path) -> None:
    script = ROOT / "scripts" / "check_sdd_gate.py"
    assert script.exists()
    _write_context_packet_fixture(tmp_path)
    spec_path = (
        tmp_path
        / "docs"
        / "sdd"
        / "features"
        / "active"
        / "2026-06-09-context-packet-fixture"
        / "spec.md"
    )
    spec_text = spec_path.read_text(encoding="utf-8")
    before, clarifications_and_rest = spec_text.split("## Clarifications", 1)
    _old_clarifications, after_clarifications = clarifications_and_rest.split("## Requirement Checklist", 1)
    spec_path.write_text(
        before
        + "## Clarifications\n\n"
        + "| Question | Answer | Approved by | Approved at |\n"
        + "|----------|--------|-------------|-------------|\n"
        + "| Should malformed tables pass? | No. | qinghuan | 2026-06-09\n\n"
        + "## Requirement Checklist"
        + after_clarifications,
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--root",
            str(tmp_path),
            "--feature",
            "2026-06-09-context-packet-fixture",
            "--gate",
            "clarify",
            "--check",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "gate-evidence-missing" in result.stderr


@pytest.mark.architecture
def test_sdd_gate_check_cli_rejects_doubled_boundary_pipes(tmp_path: Path) -> None:
    script = ROOT / "scripts" / "check_sdd_gate.py"
    assert script.exists()
    _write_context_packet_fixture(tmp_path)
    spec_path = (
        tmp_path
        / "docs"
        / "sdd"
        / "features"
        / "active"
        / "2026-06-09-context-packet-fixture"
        / "spec.md"
    )
    spec_text = spec_path.read_text(encoding="utf-8")
    before, clarifications_and_rest = spec_text.split("## Clarifications", 1)
    _old_clarifications, after_clarifications = clarifications_and_rest.split("## Requirement Checklist", 1)
    spec_path.write_text(
        before
        + "## Clarifications\n\n"
        + "|| Question | Answer | Approved by | Approved at ||\n"
        + "||----------|--------|-------------|-------------||\n"
        + "|| Should malformed tables pass? | No. | qinghuan | 2026-06-09 ||\n\n"
        + "## Requirement Checklist"
        + after_clarifications,
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--root",
            str(tmp_path),
            "--feature",
            "2026-06-09-context-packet-fixture",
            "--gate",
            "clarify",
            "--check",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "gate-evidence-missing" in result.stderr


@pytest.mark.architecture
def test_sdd_gate_check_cli_rejects_indented_table_rows(tmp_path: Path) -> None:
    script = ROOT / "scripts" / "check_sdd_gate.py"
    assert script.exists()
    _write_context_packet_fixture(tmp_path)
    spec_path = (
        tmp_path
        / "docs"
        / "sdd"
        / "features"
        / "active"
        / "2026-06-09-context-packet-fixture"
        / "spec.md"
    )
    spec_text = spec_path.read_text(encoding="utf-8")
    before, clarifications_and_rest = spec_text.split("## Clarifications", 1)
    _old_clarifications, after_clarifications = clarifications_and_rest.split("## Requirement Checklist", 1)
    spec_path.write_text(
        before
        + "## Clarifications\n\n"
        + "    | Question | Answer | Approved by | Approved at |\n"
        + "    |----------|--------|-------------|-------------|\n"
        + "    | Should indented tables pass? | No. | qinghuan | 2026-06-09 |\n\n"
        + "## Requirement Checklist"
        + after_clarifications,
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--root",
            str(tmp_path),
            "--feature",
            "2026-06-09-context-packet-fixture",
            "--gate",
            "clarify",
            "--check",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "gate-evidence-missing" in result.stderr


@pytest.mark.architecture
def test_sdd_gate_check_cli_rejects_separator_arity_mismatch(tmp_path: Path) -> None:
    script = ROOT / "scripts" / "check_sdd_gate.py"
    assert script.exists()
    _write_context_packet_fixture(tmp_path)
    spec_path = (
        tmp_path
        / "docs"
        / "sdd"
        / "features"
        / "active"
        / "2026-06-09-context-packet-fixture"
        / "spec.md"
    )
    spec_text = spec_path.read_text(encoding="utf-8")
    before, clarifications_and_rest = spec_text.split("## Clarifications", 1)
    _old_clarifications, after_clarifications = clarifications_and_rest.split("## Requirement Checklist", 1)
    spec_path.write_text(
        before
        + "## Clarifications\n\n"
        + "| Question | Answer | Approved by | Approved at |\n"
        + "|----------|--------|\n"
        + "| Should malformed tables pass? | No. | qinghuan | 2026-06-09 |\n\n"
        + "## Requirement Checklist"
        + after_clarifications,
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--root",
            str(tmp_path),
            "--feature",
            "2026-06-09-context-packet-fixture",
            "--gate",
            "clarify",
            "--check",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "gate-evidence-missing" in result.stderr


@pytest.mark.architecture
def test_sdd_gate_check_cli_rejects_body_row_arity_mismatch(tmp_path: Path) -> None:
    script = ROOT / "scripts" / "check_sdd_gate.py"
    assert script.exists()
    _write_context_packet_fixture(tmp_path)
    spec_path = (
        tmp_path
        / "docs"
        / "sdd"
        / "features"
        / "active"
        / "2026-06-09-context-packet-fixture"
        / "spec.md"
    )
    spec_text = spec_path.read_text(encoding="utf-8")
    before, clarifications_and_rest = spec_text.split("## Clarifications", 1)
    _old_clarifications, after_clarifications = clarifications_and_rest.split("## Requirement Checklist", 1)
    spec_path.write_text(
        before
        + "## Clarifications\n\n"
        + "| Question | Answer | Approved by | Approved at |\n"
        + "|----------|--------|-------------|-------------|\n"
        + "| Should malformed tables pass? | No. | qinghuan |\n\n"
        + "## Requirement Checklist"
        + after_clarifications,
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--root",
            str(tmp_path),
            "--feature",
            "2026-06-09-context-packet-fixture",
            "--gate",
            "clarify",
            "--check",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "gate-evidence-missing" in result.stderr


@pytest.mark.architecture
def test_sdd_gate_check_cli_rejects_non_contiguous_body_rows(tmp_path: Path) -> None:
    script = ROOT / "scripts" / "check_sdd_gate.py"
    assert script.exists()
    _write_context_packet_fixture(tmp_path)
    spec_path = (
        tmp_path
        / "docs"
        / "sdd"
        / "features"
        / "active"
        / "2026-06-09-context-packet-fixture"
        / "spec.md"
    )
    spec_text = spec_path.read_text(encoding="utf-8")
    before, clarifications_and_rest = spec_text.split("## Clarifications", 1)
    _old_clarifications, after_clarifications = clarifications_and_rest.split("## Requirement Checklist", 1)
    spec_path.write_text(
        before
        + "## Clarifications\n\n"
        + "| Question | Answer | Approved by | Approved at |\n"
        + "|----------|--------|-------------|-------------|\n"
        + "Body rows below this prose are not part of the Markdown table.\n"
        + "| Should malformed tables pass? | No. | qinghuan | 2026-06-09 |\n\n"
        + "## Requirement Checklist"
        + after_clarifications,
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--root",
            str(tmp_path),
            "--feature",
            "2026-06-09-context-packet-fixture",
            "--gate",
            "clarify",
            "--check",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "gate-evidence-missing" in result.stderr


@pytest.mark.architecture
def test_sdd_gate_check_cli_rejects_wrong_clarification_header(tmp_path: Path) -> None:
    script = ROOT / "scripts" / "check_sdd_gate.py"
    assert script.exists()
    _write_context_packet_fixture(tmp_path)
    spec_path = (
        tmp_path
        / "docs"
        / "sdd"
        / "features"
        / "active"
        / "2026-06-09-context-packet-fixture"
        / "spec.md"
    )
    spec_text = spec_path.read_text(encoding="utf-8")
    before, clarifications_and_rest = spec_text.split("## Clarifications", 1)
    _old_clarifications, after_clarifications = clarifications_and_rest.split("## Requirement Checklist", 1)
    spec_path.write_text(
        before
        + "## Clarifications\n\n"
        + "| Topic | Decision | Owner | Date |\n"
        + "|-------|----------|-------|------|\n"
        + "| Gate schema | Must be canonical. | qinghuan | 2026-06-09 |\n\n"
        + "## Requirement Checklist"
        + after_clarifications,
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--root",
            str(tmp_path),
            "--feature",
            "2026-06-09-context-packet-fixture",
            "--gate",
            "clarify",
            "--check",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "gate-evidence-missing" in result.stderr


@pytest.mark.architecture
def test_sdd_gate_check_cli_requires_markdown_heading_lines(tmp_path: Path) -> None:
    script = ROOT / "scripts" / "check_sdd_gate.py"
    assert script.exists()
    _write_context_packet_fixture(tmp_path)
    spec_path = (
        tmp_path
        / "docs"
        / "sdd"
        / "features"
        / "active"
        / "2026-06-09-context-packet-fixture"
        / "spec.md"
    )
    spec_text = spec_path.read_text(encoding="utf-8")
    spec_text = spec_text.replace(
        "The fixture spec is grounded by its own source record",
        "The fixture spec mentions `## Clarifications` in prose and is grounded by its own source record",
    )
    before_heading, after_heading = spec_text.rsplit("\n## Clarifications\n", 1)
    spec_text = before_heading + "\nClarifications\n" + after_heading
    spec_path.write_text(spec_text, encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--root",
            str(tmp_path),
            "--feature",
            "2026-06-09-context-packet-fixture",
            "--gate",
            "clarify",
            "--check",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "missing-gate-section" in result.stderr


@pytest.mark.architecture
def test_sdd_gate_check_cli_ignores_fenced_heading_tokens(tmp_path: Path) -> None:
    script = ROOT / "scripts" / "check_sdd_gate.py"
    assert script.exists()
    _write_context_packet_fixture(tmp_path)
    spec_path = (
        tmp_path
        / "docs"
        / "sdd"
        / "features"
        / "active"
        / "2026-06-09-context-packet-fixture"
        / "spec.md"
    )
    spec_text = spec_path.read_text(encoding="utf-8")
    spec_text = spec_text.replace(
        "The fixture spec is grounded by its own source record",
        "\n".join(
            [
                "The fixture spec is grounded by its own source record",
                "",
                "```text",
                "## Clarifications",
                "```",
                "",
            ]
        ),
    )
    before_heading, after_heading = spec_text.rsplit("\n## Clarifications\n", 1)
    spec_text = before_heading + "\nClarifications\n" + after_heading
    spec_path.write_text(spec_text, encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--root",
            str(tmp_path),
            "--feature",
            "2026-06-09-context-packet-fixture",
            "--gate",
            "clarify",
            "--check",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "missing-gate-section" in result.stderr


@pytest.mark.architecture
def test_sdd_gate_check_cli_ignores_tilde_fenced_heading_tokens(tmp_path: Path) -> None:
    script = ROOT / "scripts" / "check_sdd_gate.py"
    assert script.exists()
    _write_context_packet_fixture(tmp_path)
    spec_path = (
        tmp_path
        / "docs"
        / "sdd"
        / "features"
        / "active"
        / "2026-06-09-context-packet-fixture"
        / "spec.md"
    )
    spec_text = spec_path.read_text(encoding="utf-8")
    spec_text = spec_text.replace(
        "The fixture spec is grounded by its own source record",
        "\n".join(
            [
                "The fixture spec is grounded by its own source record",
                "",
                "~~~text",
                "## Clarifications",
                "~~~",
                "",
            ]
        ),
    )
    before_heading, after_heading = spec_text.rsplit("\n## Clarifications\n", 1)
    spec_text = before_heading + "\nClarifications\n" + after_heading
    spec_path.write_text(spec_text, encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--root",
            str(tmp_path),
            "--feature",
            "2026-06-09-context-packet-fixture",
            "--gate",
            "clarify",
            "--check",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "missing-gate-section" in result.stderr


@pytest.mark.architecture
def test_sdd_gate_check_cli_rejects_placeholder_gate_rows(tmp_path: Path) -> None:
    script = ROOT / "scripts" / "check_sdd_gate.py"
    assert script.exists()
    _write_context_packet_fixture(tmp_path)
    spec_path = (
        tmp_path
        / "docs"
        / "sdd"
        / "features"
        / "active"
        / "2026-06-09-context-packet-fixture"
        / "spec.md"
    )
    spec_text = spec_path.read_text(encoding="utf-8")
    before, clarifications_and_rest = spec_text.split("## Clarifications", 1)
    _old_clarifications, after_clarifications = clarifications_and_rest.split("## Requirement Checklist", 1)
    spec_path.write_text(
        before
        + "## Clarifications\n\n"
        + "| Question | Answer | Approved by | Approved at |\n"
        + "|----------|--------|-------------|-------------|\n"
        + "| <pending> | <pending> | <pending> | YYYY-MM-DD |\n\n"
        + "## Requirement Checklist"
        + after_clarifications,
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--root",
            str(tmp_path),
            "--feature",
            "2026-06-09-context-packet-fixture",
            "--gate",
            "clarify",
            "--check",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "gate-evidence-missing" in result.stderr


@pytest.mark.architecture
def test_sdd_gate_check_cli_rejects_non_canonical_clarification_approval_dates(tmp_path: Path) -> None:
    script = ROOT / "scripts" / "check_sdd_gate.py"
    assert script.exists()
    _write_context_packet_fixture(tmp_path)
    spec_path = (
        tmp_path
        / "docs"
        / "sdd"
        / "features"
        / "active"
        / "2026-06-09-context-packet-fixture"
        / "spec.md"
    )
    spec_text = spec_path.read_text(encoding="utf-8")
    before, clarifications_and_rest = spec_text.split("## Clarifications", 1)
    _old_clarifications, after_clarifications = clarifications_and_rest.split("## Requirement Checklist", 1)
    spec_path.write_text(
        before
        + "## Clarifications\n\n"
        + "| Question | Answer | Approved by | Approved at |\n"
        + "|----------|--------|-------------|-------------|\n"
        + "| Scope? | Harness only. | qinghuan | 20260609 |\n\n"
        + "## Requirement Checklist"
        + after_clarifications,
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--root",
            str(tmp_path),
            "--feature",
            "2026-06-09-context-packet-fixture",
            "--gate",
            "clarify",
            "--check",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "gate-evidence-missing" in result.stderr


@pytest.mark.architecture
def test_sdd_gate_check_cli_accepts_all_active_features(tmp_path: Path) -> None:
    script = ROOT / "scripts" / "check_sdd_gate.py"
    assert script.exists()
    _write_context_packet_fixture(tmp_path)
    _clone_context_packet_fixture(tmp_path, "2026-06-09-second-context-fixture")
    _create_context_packet_fixture_paths(tmp_path)

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--root",
            str(tmp_path),
            "--all-active",
            "--check",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "all active SDD gates passed" in result.stdout
    assert "2026-06-09-context-packet-fixture" in result.stdout
    assert "2026-06-09-second-context-fixture" in result.stdout


@pytest.mark.architecture
def test_sdd_gate_check_cli_rejects_any_failed_active_feature(tmp_path: Path) -> None:
    script = ROOT / "scripts" / "check_sdd_gate.py"
    assert script.exists()
    _write_context_packet_fixture(tmp_path)
    failing_slug = "2026-06-09-second-context-fixture"
    _clone_context_packet_fixture(tmp_path, failing_slug)
    _create_context_packet_fixture_paths(tmp_path)
    plan_path = tmp_path / "docs" / "sdd" / "features" / "active" / failing_slug / "plan.md"
    plan_text = plan_path.read_text(encoding="utf-8")
    plan_path.write_text(plan_text.replace("Pass: fixture", "Fail: fixture"), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--root",
            str(tmp_path),
            "--all-active",
            "--check",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert failing_slug in result.stderr
    assert "plan-analyze-gate-invalid" in result.stderr


@pytest.mark.architecture
def test_sdd_gate_check_cli_implement_rejects_delegated_artifact_drift(tmp_path: Path) -> None:
    script = ROOT / "scripts" / "check_sdd_gate.py"
    assert script.exists()
    _write_context_packet_fixture(tmp_path)
    tasks_path = (
        tmp_path
        / "docs"
        / "sdd"
        / "features"
        / "active"
        / "2026-06-09-context-packet-fixture"
        / "tasks.md"
    )
    tasks_text = tasks_path.read_text(encoding="utf-8")
    tasks_text = tasks_text.replace(
        "- **Subagent handoff**: not delegated",
        "- **Subagent handoff**: docs/generated/subagent-handoffs/missing.md",
        1,
    )
    tasks_text = tasks_text.replace(
        "- **Subagent report**: not delegated",
        "- **Subagent report**: docs/generated/subagent-reports/missing.md",
        1,
    )
    tasks_text = tasks_text.replace("- **Review result**: parent-reviewed", "- **Review result**: accepted", 1)
    tasks_path.write_text(tasks_text, encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--root",
            str(tmp_path),
            "--feature",
            "2026-06-09-context-packet-fixture",
            "--gate",
            "implement",
            "--check",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "task-missing-subagent-report-artifact" in result.stderr
    assert "task-missing-subagent-handoff-artifact" in result.stderr


@pytest.mark.architecture
def test_sdd_gate_check_cli_implement_rejects_missing_task_gate_compliance(tmp_path: Path) -> None:
    script = ROOT / "scripts" / "check_sdd_gate.py"
    assert script.exists()
    _write_context_packet_fixture(tmp_path)
    tasks_path = (
        tmp_path
        / "docs"
        / "sdd"
        / "features"
        / "active"
        / "2026-06-09-context-packet-fixture"
        / "tasks.md"
    )
    tasks_text = tasks_path.read_text(encoding="utf-8")
    before, gate_and_rest = tasks_text.split("## Gate Compliance", 1)
    _old_gate, rest = gate_and_rest.split("## Tasks", 1)
    tasks_path.write_text(before + "## Tasks" + rest, encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--root",
            str(tmp_path),
            "--feature",
            "2026-06-09-context-packet-fixture",
            "--gate",
            "implement",
            "--check",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "missing-gate-section" in result.stderr
    assert "tasks.md" in result.stderr


@pytest.mark.architecture
def test_sdd_gate_check_cli_implement_rejects_incomplete_task_gate_compliance(tmp_path: Path) -> None:
    script = ROOT / "scripts" / "check_sdd_gate.py"
    assert script.exists()
    _write_context_packet_fixture(tmp_path)
    tasks_path = (
        tmp_path
        / "docs"
        / "sdd"
        / "features"
        / "active"
        / "2026-06-09-context-packet-fixture"
        / "tasks.md"
    )
    tasks_text = tasks_path.read_text(encoding="utf-8")
    before, gate_and_rest = tasks_text.split("## Gate Compliance", 1)
    _old_gate, rest = gate_and_rest.split("## Tasks", 1)
    tasks_path.write_text(
        before
        + "## Gate Compliance\n\n"
        + "| Gate | Evidence |\n"
        + "|------|----------|\n"
        + "| Clarify | `spec.md` includes `## Clarifications`. |\n"
        + "| Checklist | `spec.md` includes `## Requirement Checklist`. |\n"
        + "| Analyze | `plan.md` includes `## Analyze Gate`. |\n\n"
        + "## Tasks"
        + rest,
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--root",
            str(tmp_path),
            "--feature",
            "2026-06-09-context-packet-fixture",
            "--gate",
            "implement",
            "--check",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "gate-evidence-missing" in result.stderr
    assert "tasks.md" in result.stderr


@pytest.mark.architecture
def test_subagent_report_validator_accepts_evidence_report(tmp_path: Path) -> None:
    script = ROOT / "scripts" / "validate_subagent_report.py"
    report = tmp_path / "subagent-report.md"
    report.write_text(
        dedent(
            """
            # Subagent Report

            Mode: read-only

            ## Findings

            - No issues found in `scripts/dispatch_sdd_task.py`.

            ## Scope Adherence

            - Owned scope: pass
            - Conflict set: pass

            ## Changed Files

            - none

            ## Verification Evidence

            ```text
            $ uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_context_packet_cli -q
            1 passed
            exit code: 0
            ```

            ## Remaining Risks

            - Integration/e2e gates were not run by instruction.
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(script), "--mode", "read-only", "--report", str(report)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Subagent report validation passed." in result.stdout


@pytest.mark.architecture
def test_subagent_report_validator_rejects_unverifiable_or_out_of_scope_report(tmp_path: Path) -> None:
    script = ROOT / "scripts" / "validate_subagent_report.py"
    report = tmp_path / "subagent-report.md"
    report.write_text(
        dedent(
            """
            # Subagent Report

            Mode: read-only

            ## Findings

            - Looks fine.

            ## Scope Adherence

            - Owned scope: pass
            - Conflict set: pass

            ## Changed Files

            - `scripts/dispatch_sdd_task.py`

            ## Verification Evidence

            ```text
            $ uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_context_packet_cli -q
            passed
            ```

            ## Remaining Risks

            - none
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    result = subprocess.run(
        [sys.executable, str(script), "--mode", "read-only", "--report", str(report)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "read-only reports must not list changed files" in result.stderr
    assert "verification evidence requires a command block with exit code" in result.stderr


@pytest.mark.architecture
def test_subagent_report_validator_accepts_task_bound_report(tmp_path: Path) -> None:
    script = ROOT / "scripts" / "validate_subagent_report.py"
    _write_context_packet_fixture(tmp_path)
    report = tmp_path / "subagent-report.md"
    report.write_text(
        _subagent_report(
            mode="read-only",
            changed_files="- none",
            command="uv run pytest tests/architecture/test_agent_playbook_contracts.py -q",
            exit_code=0,
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--root",
            str(tmp_path),
            "--feature",
            "2026-06-09-context-packet-fixture",
            "--task",
            "1",
            "--mode",
            "read-only",
            "--report",
            str(report),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.architecture
def test_subagent_report_validator_requires_task_classification_and_required_reading_evidence(tmp_path: Path) -> None:
    script = ROOT / "scripts" / "validate_subagent_report.py"
    _write_context_packet_fixture(tmp_path)
    report = tmp_path / "subagent-report.md"
    report.write_text(
        _subagent_report(
            mode="read-only",
            changed_files="- none",
            command="uv run pytest tests/architecture/test_agent_playbook_contracts.py -q",
            exit_code=0,
            required_reading_evidence=False,
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--root",
            str(tmp_path),
            "--feature",
            "2026-06-09-context-packet-fixture",
            "--task",
            "1",
            "--mode",
            "read-only",
            "--report",
            str(report),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "required reading evidence requires `Task classification:`" in result.stderr
    assert "required reading evidence must include `AGENTS.md`" in result.stderr
    assert "required reading evidence must include `docs/agent-playbook/task-reading-matrix.md`" in result.stderr


@pytest.mark.architecture
def test_subagent_report_validator_rejects_task_bound_scope_and_command_drift(tmp_path: Path) -> None:
    script = ROOT / "scripts" / "validate_subagent_report.py"
    _write_context_packet_fixture(tmp_path)
    report = tmp_path / "subagent-report.md"
    report.write_text(
        _subagent_report(
            mode="write-allowed",
            changed_files="- `scripts/dispatch_sdd_task.py`",
            command="uv run pytest tests/architecture/test_sdd_artifact_validator.py -q",
            exit_code=1,
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--root",
            str(tmp_path),
            "--feature",
            "2026-06-09-context-packet-fixture",
            "--task",
            "1",
            "--mode",
            "write-allowed",
            "--report",
            str(report),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "changed files must stay within task touch set" in result.stderr
    assert "verification command must match task verification" in result.stderr
    assert "verification command exit code must be 0" in result.stderr


@pytest.mark.architecture
def test_development_agent_eval_repair_loop_is_defined() -> None:
    text = _read(PLAYBOOK / "eval-repair-loop.md")
    for required_phrase in (
        "## Trace Dataset",
        "## Metrics",
        "## Repair Loop",
        "review defect",
        "token cost",
        "harness failure",
        "make check-all",
        "No production claim without verification evidence",
        "validated subagent reports",
        "scripts/validate_subagent_report.py",
    ):
        assert required_phrase in text


@pytest.mark.architecture
def test_agent_execution_doc_keeps_runtime_agent_boundary_explicit() -> None:
    text = _read(ROOT / "docs" / "AGENT_EXECUTION.md")
    for required_phrase in (
        "AgentExecutionGateway",
        "PostgreSQL facts remain truth",
        "There is no central durable `agent_tasks` queue",
        "development agents",
        "product LLM agents",
    ):
        assert required_phrase in text


@pytest.mark.architecture
def test_tasks_template_has_parallel_subagent_contract_fields() -> None:
    text = _read(ROOT / "docs" / "sdd" / "_templates" / "tasks-template.md")
    for required_phrase in (
        "**Status**",
        "**Branch**",
        "**Approved by**",
        "**Approved at**",
        "## Gate Compliance",
        "**Owner**",
        "**Depends on**",
        "**Touch set**",
        "**Conflict set**",
        "**Subagent handoff**",
        "**Subagent report**",
        "**Review result**",
        "**Review owner**",
        "**Factory lane**",
        "**Deterministic constraints**",
        "**On-demand context**",
        "**Kill/defer criteria**",
        "**Eval/repair signal**",
    ):
        assert required_phrase in text


@pytest.mark.architecture
def test_tasks_template_does_not_duplicate_final_verification_surface() -> None:
    text = _read(ROOT / "docs" / "sdd" / "_templates" / "tasks-template.md")

    assert "## Final verification" not in text
    assert "After all tasks are `[x] complete`" not in text


@pytest.mark.architecture
def test_sdd_work_index_is_generated_and_current() -> None:
    script = ROOT / "scripts" / "regen_sdd_work_index.py"
    validator = ROOT / "scripts" / "validate_sdd_artifacts.py"
    generated = ROOT / "docs" / "generated" / "sdd-work-index.md"
    assert script.exists()
    assert validator.exists()
    assert generated.exists()
    text = generated.read_text(encoding="utf-8")
    assert render_index(scan_sdd_features(ROOT), validate_sdd_root(ROOT)) == text
    assert "## Coordination Board" in text
    assert "## Task Board" in text
    lifecycle_codes = _table_values(text, "## Lifecycle Flags", column=0)
    assert lifecycle_codes == set(KNOWN_ISSUE_CODES)
    for required_column in (
        "Owner",
        "Worktree",
        "Branch",
        "Factory lanes",
        "Touch set",
        "Conflict set",
        "Blocked",
        "Verification",
    ):
        assert required_column in text
    result = subprocess.run(
        [sys.executable, str(script), "--check"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    validation = subprocess.run(
        [sys.executable, str(validator), "--check"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert validation.returncode == 0, validation.stdout + validation.stderr


@pytest.mark.architecture
def test_sdd_work_index_summary_counts_present_artifacts_only(tmp_path: Path) -> None:
    feature_path = tmp_path / "docs" / "sdd" / "features" / "active" / "fixture"
    present = ArtifactRecord(
        name="spec.md",
        path=feature_path / "spec.md",
        relative_path="docs/sdd/features/active/fixture/spec.md",
        text="",
        status="In Progress",
        fields={},
    )
    missing = ArtifactRecord(
        name="plan.md",
        path=feature_path / "plan.md",
        relative_path="docs/sdd/features/active/fixture/plan.md",
        text="",
        status="missing-file",
        fields={},
        missing=True,
    )
    feature = SddFeature(
        slug="fixture",
        state="active",
        path=feature_path,
        relative_path="docs/sdd/features/active/fixture",
        artifacts={"spec.md": present, "plan.md": missing},
        tasks=(),
    )

    text = render_index([feature], [])

    assert "| `active` | 1 | 1 |" in text


@pytest.mark.architecture
def test_sdd_work_index_keeps_conflict_coordination_rule_intact(tmp_path: Path) -> None:
    feature_path = tmp_path / "docs" / "sdd" / "features" / "active" / "fixture"
    feature = SddFeature(
        slug="fixture",
        state="active",
        path=feature_path,
        relative_path="docs/sdd/features/active/fixture",
        artifacts={},
        tasks=(
            TaskRecord(
                title="Task 1",
                fields={
                    "conflict set": (
                        "coordinate with 2026-06-09-other-feature for shared SDD index, macro repository, "
                        "and agent playbook test edits"
                    )
                },
            ),
        ),
    )

    text = render_index([feature], [])

    assert (
        "`coordinate with 2026-06-09-other-feature for shared SDD index, macro repository, "
        "and agent playbook test edits`"
    ) in text
    assert "`macro repository`" not in text
    assert "`and agent playbook test edits`" not in text


@pytest.mark.architecture
def test_sdd_work_index_renders_task_dispatch_board(tmp_path: Path) -> None:
    feature_path = tmp_path / "docs" / "sdd" / "features" / "active" / "fixture"
    feature = SddFeature(
        slug="fixture",
        state="active",
        path=feature_path,
        relative_path="docs/sdd/features/active/fixture",
        artifacts={},
        tasks=(
            TaskRecord(
                title="Task 1 — Build harness",
                fields={
                    "status": "[~]",
                    "factory lane": "Harness/tests",
                    "owner": "parent",
                    "depends on": "none",
                    "touch set": "scripts/build_agent_context_packet.py",
                    "conflict set": "coordinate with other-feature for context packet docs",
                    "subagent report": "not delegated",
                    "review result": "parent-reviewed",
                    "verification": "uv run pytest tests/architecture/test_agent_playbook_contracts.py -q",
                },
            ),
            TaskRecord(
                title="Task 2 — Completed docs",
                fields={
                    "status": "[x]",
                    "factory lane": "Docs/contracts",
                    "owner": "parent",
                    "depends on": "none",
                    "touch set": "docs/agent-playbook/context-packet-template.md",
                    "conflict set": "docs/agent-playbook/factory-operating-model.md",
                    "subagent report": "docs/generated/subagent-reports/task-2.md",
                    "review result": "accepted",
                    "verification": "uv run pytest tests/architecture/test_agent_playbook_contracts.py -q",
                },
            ),
            TaskRecord(
                title="Task 3 — Blocked dispatch",
                fields={
                    "status": "[~]",
                    "factory lane": "Harness/tests",
                    "owner": "parent",
                    "depends on": "Task 1",
                    "touch set": "scripts/dispatch_sdd_task.py",
                    "conflict set": "coordinate with other-feature for dispatcher docs",
                    "subagent report": "docs/generated/subagent-reports/task-3.md",
                    "review result": "needs-repair",
                    "verification": "uv run pytest tests/architecture/test_agent_playbook_contracts.py -q",
                },
            ),
        ),
    )

    text = render_index([feature], [])

    assert "## Task Board" in text
    assert (
        "| `fixture` | `Task 1 — Build harness` | `[~]` | `dispatchable` | `Harness/tests` | parent | none | "
        "`scripts/build_agent_context_packet.py` | "
        "`coordinate with other-feature for context packet docs` | "
        "`not delegated` | `parent-reviewed` | "
        "`uv run pytest tests/architecture/test_agent_playbook_contracts.py -q` |"
    ) in text
    assert (
        "| `fixture` | `Task 2 — Completed docs` | `[x]` | `complete` | `Docs/contracts` | parent | none | "
        "`docs/agent-playbook/context-packet-template.md` | "
        "`docs/agent-playbook/factory-operating-model.md` | "
        "`docs/generated/subagent-reports/task-2.md` | `accepted` | "
        "`uv run pytest tests/architecture/test_agent_playbook_contracts.py -q` |"
    ) in text
    assert (
        "| `fixture` | `Task 3 — Blocked dispatch` | `[~]` | `needs-repair` | "
        "`Harness/tests` | parent | Task 1 | "
        "`scripts/dispatch_sdd_task.py` | "
        "`coordinate with other-feature for dispatcher docs` | "
        "`docs/generated/subagent-reports/task-3.md` | `needs-repair` | "
        "`uv run pytest tests/architecture/test_agent_playbook_contracts.py -q` |"
    ) in text


def _table_values(text: str, heading: str, *, column: int) -> set[str]:
    section = text.split(heading, 1)[1].split("\n## ", 1)[0]
    values: set[str] = set()
    for line in section.splitlines():
        if not line.startswith("| `"):
            continue
        cells = [cell.strip().strip("`") for cell in line.strip("|").split("|")]
        if len(cells) > column:
            values.add(cells[column])
    return values


def _subagent_report(
    *,
    mode: str,
    changed_files: str,
    command: str,
    exit_code: int,
    required_reading_evidence: bool = True,
) -> str:
    sections = [
        dedent(
            f"""
            # Subagent Report

            Mode: {mode}

            ## Findings

            - Findings are tied to the active SDD task.

            ## Scope Adherence

            - Owned scope: pass
            - Conflict set: pass
            """
        ).strip()
    ]
    if required_reading_evidence:
        sections.append(
            dedent(
                """
                ## Required Reading Evidence

                - Task classification: Harness/tests
                - Required reading checked:
                  - `AGENTS.md`
                  - `docs/agent-playbook/task-reading-matrix.md`
                  - `docs/agent-playbook/context-packet-template.md`
                """
            ).strip()
        )

    sections.append(
        dedent(
            f"""
            ## Changed Files

            {changed_files}

            ## Verification Evidence

            ```text
            $ {command}
            command output recorded
            exit code: {exit_code}
            ```

            ## Remaining Risks

            - Integration/e2e gates were not run by instruction.
            """
        ).strip()
    )
    return "\n\n".join(sections) + "\n"


def _write_context_packet_fixture(root: Path) -> None:
    feature = root / "docs" / "sdd" / "features" / "active" / "2026-06-09-context-packet-fixture"
    feature.mkdir(parents=True)
    (feature / "spec.md").write_text(
        dedent(
            """
            # Spec

            **Status**: In Progress
            **Date**: 2026-06-09
            **Owner**: Codex
            **Approved by**: qinghuan
            **Approved at**: 2026-06-09

            ## Background

            The fixture spec is grounded by its own source record
            (`docs/sdd/features/active/2026-06-09-context-packet-fixture/spec.md:1`).

            ## Clarifications

            | Question | Answer | Approved by | Approved at |
            |----------|--------|-------------|-------------|
            | Should packet generation use active SDD task metadata? | Yes. | qinghuan | 2026-06-09 |

            ## Requirement Checklist

            | Requirement | Quality gate |
            |-------------|--------------|
            | Context packet is bounded. | Generated from one task. |

            ## Acceptance criteria

            - AC1. WHEN the context packet CLI reads an active task THEN it SHALL emit a bounded packet.
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    (feature / "plan.md").write_text(
        dedent(
            """
            # Plan

            **Status**: In Progress
            **Date**: 2026-06-09
            **Owning spec**: `docs/sdd/features/active/2026-06-09-context-packet-fixture/spec.md`
            **Worktree**: `.worktrees/context-packet-fixture`
            **Branch**: `codex/context-packet-fixture`
            **Approved by**: qinghuan
            **Approved at**: 2026-06-09

            ## Analyze Gate

            | Check | Result |
            |-------|--------|
            | Product runtime untouched. | Pass: fixture only exercises development-agent harness. |

            ## Acceptance test commands

            - AC1: `uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_context_packet_cli -q`
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    (feature / "tasks.md").write_text(
        dedent(
            """
            # Tasks

            **Status**: In Progress
            **Owning plan**: `docs/sdd/features/active/2026-06-09-context-packet-fixture/plan.md`
            **Worktree**: `.worktrees/context-packet-fixture`
            **Branch**: `codex/context-packet-fixture`
            **Approved by**: qinghuan
            **Approved at**: 2026-06-09

            ## Gate Compliance

            | Gate | Evidence |
            |------|----------|
            | Clarify | `spec.md` includes `## Clarifications`. |
            | Checklist | `spec.md` includes `## Requirement Checklist`. |
            | Analyze | `plan.md` includes `## Analyze Gate`. |
            | Implement | Tasks below are TDD ordered. |
            | Verify | `verification.md` captures command output. |

            ## Tasks

            ### Task 1 — Dispatch packet

            - **File(s)**: `scripts/build_agent_context_packet.py`
            - **Owner**: parent
            - **Depends on**: none
            - **Touch set**: `scripts/build_agent_context_packet.py`
            - **Conflict set**: coordinate with 2026-06-09-other-feature for context packet generator, docs, and tests.
            - **Failing test first**: `tests/architecture/test_agent_playbook_contracts.py::test_context_packet_cli`
            - **Subagent handoff**: not delegated
            - **Subagent report**: not delegated
            - **Review result**: parent-reviewed
            - **Factory lane**: Harness/tests
            - **Deterministic constraints**: Run validator before emitting context.
            - **On-demand context**: `docs/agent-playbook/context-packet-template.md`
            - **Kill/defer criteria**: Stop if inactive SDD records are accepted.
            - **Eval/repair signal**: context packet CLI failure and review defect.
            - **Implementation**: Emit a bounded packet from one active task.
            - **Verification**: `uv run pytest tests/architecture/test_agent_playbook_contracts.py -q`
            - **Review owner**: parent
            - **Status**: [~]

            ### Task 2 — Completed packet

            - **File(s)**: `docs/agent-playbook/context-packet-template.md`
            - **Owner**: parent
            - **Depends on**: none
            - **Touch set**: `docs/agent-playbook/context-packet-template.md`
            - **Conflict set**: coordinate with 2026-06-09-other-feature for context packet docs.
            - **Failing test first**: `tests/architecture/test_agent_playbook_contracts.py::test_context_packet_cli`
            - **Subagent handoff**: not delegated
            - **Subagent report**: not delegated
            - **Review result**: parent-reviewed
            - **Factory lane**: Docs/contracts
            - **Deterministic constraints**: Completed tasks are not dispatchable.
            - **On-demand context**: `docs/agent-playbook/context-packet-template.md`
            - **Kill/defer criteria**: Stop if dispatcher accepts completed tasks.
            - **Eval/repair signal**: dispatch guard failure and review defect.
            - **Implementation**: Exercise the completed-task dispatch guard.
            - **Verification**: `uv run pytest tests/architecture/test_agent_playbook_contracts.py -q`
            - **Review owner**: parent
            - **Status**: [x]

            ### Task 3 — Blocked packet

            - **File(s)**: `scripts/dispatch_sdd_task.py`
            - **Owner**: parent
            - **Depends on**: Task 1
            - **Touch set**: `scripts/dispatch_sdd_task.py`
            - **Conflict set**: coordinate with 2026-06-09-other-feature for dispatch docs.
            - **Failing test first**: `pytest tests/architecture/test_agent_playbook_contracts.py -q`
            - **Subagent handoff**: not delegated
            - **Subagent report**: not delegated
            - **Review result**: parent-reviewed
            - **Factory lane**: Harness/tests
            - **Deterministic constraints**: Dependencies must be complete before dispatch.
            - **On-demand context**: `scripts/dispatch_sdd_task.py`
            - **Kill/defer criteria**: Stop if dispatcher accepts tasks with incomplete dependencies.
            - **Eval/repair signal**: dispatch dependency guard failure and review defect.
            - **Implementation**: Exercise the dependency dispatch guard.
            - **Verification**: `uv run pytest tests/architecture/test_agent_playbook_contracts.py -q`
            - **Review owner**: parent
            - **Status**: [~]
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    (feature / "verification.md").write_text(
        dedent(
            """
            # Verification

            **Status**: In Progress
            **Date**: 2026-06-09
            **Owning spec**: `docs/sdd/features/active/2026-06-09-context-packet-fixture/spec.md`
            **Owning plan**: `docs/sdd/features/active/2026-06-09-context-packet-fixture/plan.md`
            **Branch**: `codex/context-packet-fixture`
            **Worktree**: `.worktrees/context-packet-fixture`
            **Approved by**: qinghuan
            **Approved at**: 2026-06-09

            ## Spec compliance

            | Acceptance criterion | Status | Evidence |
            |----------------------|--------|----------|
            | AC1 | In Progress | Pending. |

            ## Verification commands

            ```text
            $ uv run pytest tests/architecture/test_agent_playbook_contracts.py::test_context_packet_cli -q
            Pending.
            ```

            ## Other commands run

            ```text
            $ uv run pytest tests/architecture/test_agent_playbook_contracts.py -q
            1 passed in 0.01s
            exit code: 0
            ```

            ## Coverage

            | metric | value | threshold | status |
            |--------|-------|-----------|--------|
            | line | Pending | >= 80% | Pending |

            ## Skipped tests

            Number of skipped tests in the run above: 0

            ## E2E golden path

            - [ ] Not applicable.
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )
    _create_context_packet_fixture_paths(root)


def _clone_context_packet_fixture(root: Path, slug: str) -> None:
    source = root / "docs" / "sdd" / "features" / "active" / "2026-06-09-context-packet-fixture"
    target = root / "docs" / "sdd" / "features" / "active" / slug
    target.mkdir(parents=True)
    source_slug = "2026-06-09-context-packet-fixture"
    source_worktree = "context-packet-fixture"
    target_worktree = slug.removeprefix("2026-06-09-")
    for source_path in source.glob("*.md"):
        text = source_path.read_text(encoding="utf-8")
        text = text.replace(source_slug, slug).replace(source_worktree, target_worktree)
        (target / source_path.name).write_text(text, encoding="utf-8")


def _create_context_packet_fixture_paths(root: Path) -> None:
    for repo_path in (
        "scripts/build_agent_context_packet.py",
        "scripts/dispatch_sdd_task.py",
        "docs/agent-playbook/context-packet-template.md",
    ):
        path = root / repo_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch(exist_ok=True)


@pytest.mark.architecture
def test_router_shared_blocks_match_and_reference_agent_playbook() -> None:
    agents = _shared_router_block(ROOT / "AGENTS.md")
    claude = _shared_router_block(ROOT / "CLAUDE.md")
    assert agents == claude
    assert "docs/agent-playbook/task-reading-matrix.md" in agents
    assert "docs/AGENT_EXECUTION.md" in agents


@pytest.mark.architecture
def test_agent_router_frontend_guardrails_match_css_harness() -> None:
    agents = _shared_router_block(ROOT / "AGENTS.md")
    retired_buckets = _typescript_string_set(
        ROOT / "web" / "tests" / "architecture" / "cssArchitectureHarness.test.ts",
        "retiredGlobalCssBuckets",
    )

    for bucket in retired_buckets:
        assert f"`{bucket}`" in agents


def _shared_router_block(path: Path) -> str:
    text = _read(path)
    start = "<!-- BEGIN SHARED AGENT ROUTER -->"
    end = "<!-- END SHARED AGENT ROUTER -->"
    assert start in text and end in text, f"{path.name} missing shared router markers"
    return text.split(start, 1)[1].split(end, 1)[0].strip()


def _typescript_string_set(path: Path, variable_name: str) -> list[str]:
    match = re.search(rf"const {variable_name} = new Set\(\[([\s\S]*?)\]\);", _read(path))
    assert match is not None, f"{variable_name} must be declared as a string Set"
    return re.findall(r'"([^"]+)"', match.group(1))
