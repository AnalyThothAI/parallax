from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

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
def test_subagent_handoff_templates_define_context_and_conflict_contracts() -> None:
    handoff = _read(PLAYBOOK / "subagent-handoff-template.md")
    context = _read(PLAYBOOK / "context-packet-template.md")

    for required_phrase in (
        "Mode",
        "Owned scope",
        "Must read",
        "Do not touch",
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
        "**Owner**",
        "**Depends on**",
        "**Touch set**",
        "**Conflict set**",
        "**Subagent handoff**",
        "**Review owner**",
        "make check-all",
    ):
        assert required_phrase in text


@pytest.mark.architecture
def test_sdd_work_index_is_generated_and_current() -> None:
    script = ROOT / "scripts" / "regen_sdd_work_index.py"
    generated = ROOT / "docs" / "generated" / "sdd-work-index.md"
    assert script.exists()
    assert generated.exists()
    text = generated.read_text(encoding="utf-8")
    assert "| `review-lifecycle` | 0 |" in text
    assert "| `missing-status` | 0 |" in text
    result = subprocess.run(
        [sys.executable, str(script), "--check"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.architecture
def test_router_shared_blocks_match_and_reference_agent_playbook() -> None:
    agents = _shared_router_block(ROOT / "AGENTS.md")
    claude = _shared_router_block(ROOT / "CLAUDE.md")
    assert agents == claude
    assert "docs/agent-playbook/task-reading-matrix.md" in agents
    assert "docs/AGENT_EXECUTION.md" in agents


def _shared_router_block(path: Path) -> str:
    text = _read(path)
    start = "<!-- BEGIN SHARED AGENT ROUTER -->"
    end = "<!-- END SHARED AGENT ROUTER -->"
    assert start in text and end in text, f"{path.name} missing shared router markers"
    return text.split(start, 1)[1].split(end, 1)[0].strip()
