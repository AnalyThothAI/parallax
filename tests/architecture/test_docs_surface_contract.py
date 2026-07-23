from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
GENERATED_FILES = {
    "README.md",
    "cli-help.md",
    "db-schema.md",
    "openapi.json",
    "score-versions.md",
    "sdd-work-index.md",
    "ws-protocol.md",
}
CANONICAL_DOCS = {
    "ARCHITECTURE.md",
    "CONTRACTS.md",
    "DEVELOPMENT.md",
    "FRONTEND.md",
    "OPERATIONS.md",
    "SECURITY.md",
    "SETUP.md",
}
MARKDOWN_LINK_RE = re.compile(r"\[[^\]]+\]\((?P<target>[^)]+)\)")


def test_docs_tree_has_one_small_canonical_surface() -> None:
    for retired in (
        "AGENT_EXECUTION.md",
        "DESIGN_DISCIPLINE.md",
        "RELIABILITY.md",
        "TECH_DEBT.md",
        "TESTING.md",
        "WORKERS.md",
        "WORKER_FLOW.md",
        "WORKFLOW.md",
        "agent-playbook",
        "mockups",
        "prototypes",
        "reviews",
    ):
        assert not (DOCS / retired).exists(), f"retired docs surface remains: docs/{retired}"

    actual = {path.name for path in DOCS.glob("*.md")}
    assert actual == CANONICAL_DOCS

    for required in CANONICAL_DOCS:
        assert (DOCS / required).is_file(), f"missing canonical doc: docs/{required}"


def test_generated_tree_contains_only_reproducible_outputs() -> None:
    generated = DOCS / "generated"
    actual = {
        path.relative_to(generated).as_posix()
        for path in generated.rglob("*")
        if path.is_file()
    }
    assert actual == GENERATED_FILES


def test_retired_agent_coordination_harness_is_absent() -> None:
    for retired in (
        "agent_mode_constraints.py",
        "build_agent_context_packet.py",
        "dispatch_sdd_task.py",
        "subagent_report_contract.py",
        "validate_subagent_report.py",
    ):
        assert not (ROOT / "scripts" / retired).exists(), f"retired agent harness remains: scripts/{retired}"


def test_current_documentation_links_resolve() -> None:
    sources = [
        ROOT / "README.md",
        *(DOCS / name for name in CANONICAL_DOCS),
        DOCS / "generated" / "README.md",
        DOCS / "references" / "README.md",
        DOCS / "sdd" / "README.md",
        DOCS / "sdd" / "_templates" / "README.md",
    ]
    missing: list[str] = []
    for source in sources:
        for match in MARKDOWN_LINK_RE.finditer(source.read_text(encoding="utf-8")):
            target = match.group("target").strip().strip("<>")
            if target.startswith(("http://", "https://", "#")):
                continue
            target_path = target.split("#", 1)[0]
            if target_path and not (source.parent / target_path).resolve().exists():
                missing.append(f"{source.relative_to(ROOT)} -> {target}")
    assert not missing, "broken current documentation links:\n" + "\n".join(missing)


def test_agent_router_shared_blocks_match() -> None:
    def shared_block(path: Path) -> str:
        text = path.read_text(encoding="utf-8")
        return text.split("<!-- BEGIN SHARED AGENT ROUTER -->", 1)[1].split(
            "<!-- END SHARED AGENT ROUTER -->",
            1,
        )[0]

    assert shared_block(ROOT / "AGENTS.md") == shared_block(ROOT / "CLAUDE.md")
