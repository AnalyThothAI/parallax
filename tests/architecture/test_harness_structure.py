"""Structural assertions for the docs harness.

Each test maps to an acceptance criterion in
docs/superpowers/specs/completed/2026-05-09-harness-engineering-restructure.md.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DOCS = REPO_ROOT / "docs"
SUPERPOWERS = DOCS / "superpowers"

EXPECTED_GOVERNANCE = {
    "ARCHITECTURE.md",
    "CONTRACTS.md",
    "SETUP.md",
    "WORKFLOW.md",
    "DESIGN_DISCIPLINE.md",
    "TESTING.md",
    "SECURITY.md",
    "RELIABILITY.md",
    "FRONTEND.md",
    "TECH_DEBT.md",
}

ROUTER_FILES = ("AGENTS.md", "CLAUDE.md")

RULE_PHRASES = {
    "Single ASGI worker": "RELIABILITY.md",
    "`projection_version` and `factor_version` are bumped": "CONTRACTS.md",
    "Integration tests should hit a real PostgreSQL": "TESTING.md",
    "git worktree add .worktrees": "WORKFLOW.md",
    "Audit before design": "DESIGN_DISCIPLINE.md",
    "Single config source": "SECURITY.md",
}


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def test_routers_within_line_budget() -> None:
    for name in ROUTER_FILES:
        path = REPO_ROOT / name
        line_count = len(_read(path).splitlines())
        assert line_count <= 60, f"{name} has {line_count} lines, expected <= 60"


def test_lane_roots_have_no_loose_files() -> None:
    for lane in ("specs", "plans"):
        lane_root = SUPERPOWERS / lane
        loose_md = sorted(p.name for p in lane_root.glob("*.md"))
        assert loose_md == [], f"{lane}/ root holds loose files: {loose_md}"
        children = sorted(p.name for p in lane_root.iterdir() if not p.name.startswith("."))
        assert set(children) == {"active", "completed"}, children


def test_specs_lane_has_templates_dir_only_under_superpowers() -> None:
    children = sorted(p.name for p in SUPERPOWERS.iterdir() if not p.name.startswith("."))
    assert set(children) == {"_templates", "specs", "plans"}, children


def test_docs_root_governance_files() -> None:
    actual = {p.name for p in DOCS.glob("*.md")}
    assert actual == EXPECTED_GOVERNANCE, f"unexpected docs root contents: {actual ^ EXPECTED_GOVERNANCE}"


def test_no_legacy_files_at_docs_root() -> None:
    legacy = sorted(p.name for p in DOCS.glob("2026-*-cn.md"))
    legacy += sorted(p.name for p in DOCS.glob("token-radar-social-heat-*.md"))
    assert legacy == [], f"legacy files still at docs root: {legacy}"


def test_rule_uniqueness() -> None:
    governance_paths = {name: DOCS / name for name in EXPECTED_GOVERNANCE}
    for phrase, expected_owner in RULE_PHRASES.items():
        hits = [name for name, path in governance_paths.items() if path.exists() and phrase in _read(path)]
        assert hits == [expected_owner], f"phrase {phrase!r} expected only in {expected_owner}, found in {hits}"
        for router in ROUTER_FILES:
            assert phrase not in _read(REPO_ROOT / router), f"phrase {phrase!r} leaked into {router}"


def test_references_papers_present() -> None:
    papers_dir = DOCS / "references" / "papers"
    assert papers_dir.is_dir(), "docs/references/papers/ missing"
    expected = {
        "kleinberg-2002-burst.md",
        "goel-2016-structural-virality.md",
        "cheng-2014-cascades.md",
        "bakshy-2011-influencer-refutation.md",
        "centola-2010-complex-contagion.md",
        "crane-sornette-2008-endogenous-exogenous.md",
    }
    actual = {p.name for p in papers_dir.glob("*.md")}
    assert actual == expected, f"papers missing or extra: {actual ^ expected}"
