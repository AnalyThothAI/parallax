"""Structural assertions for the docs harness."""

from __future__ import annotations

import os
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DOCS = REPO_ROOT / "docs"
SDD = DOCS / "sdd"

EXPECTED_GOVERNANCE = {
    "ARCHITECTURE.md",
    "AGENT_EXECUTION.md",
    "CONTRACTS.md",
    "SETUP.md",
    "WORKFLOW.md",
    "DESIGN_DISCIPLINE.md",
    "TESTING.md",
    "SECURITY.md",
    "RELIABILITY.md",
    "FRONTEND.md",
    "WORKERS.md",
    "WORKER_FLOW.md",
    "TECH_DEBT.md",
}

ROUTER_FILES = ("AGENTS.md", "CLAUDE.md")
LEGACY_SDD_TOKEN = "docs" + "/superpowers"
SCANNED_SUFFIXES = {".md", ".py", ".toml", ".yaml", ".yml"}
SKIPPED_DIRS = {
    ".codex",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    ".worktrees",
    "__pycache__",
    "node_modules",
}

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


def _scanned_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for current_root, dirs, filenames in os.walk(root):
        dirs[:] = [name for name in dirs if name not in SKIPPED_DIRS]
        current = Path(current_root)
        for filename in filenames:
            path = current / filename
            if path.name == "test_harness_structure.py":
                continue
            if path.suffix not in SCANNED_SUFFIXES and path.name != "Makefile":
                continue
            files.append(path)
    return files


def test_routers_within_line_budget() -> None:
    for name in ROUTER_FILES:
        path = REPO_ROOT / name
        line_count = len(_read(path).splitlines())
        assert line_count <= 60, f"{name} has {line_count} lines, expected <= 60"


def test_legacy_superpowers_tree_is_removed() -> None:
    assert not (DOCS / "superpowers").exists(), "legacy SDD tree must not remain as a compatibility lane"


def test_current_governance_does_not_reference_legacy_superpowers_paths() -> None:
    offenders: list[str] = []
    for path in _scanned_files(REPO_ROOT):
        text = path.read_text(encoding="utf-8")
        if LEGACY_SDD_TOKEN in text:
            offenders.append(path.relative_to(REPO_ROOT).as_posix())

    assert offenders == [], f"legacy SDD path references remain: {offenders}"


def test_sdd_feature_tree_has_no_loose_lane_files() -> None:
    for lane in ("active", "completed"):
        lane_root = SDD / "features" / lane
        loose_md = sorted(p.name for p in lane_root.glob("*.md"))
        assert loose_md == [], f"features/{lane}/ root holds loose files: {loose_md}"
        for feature in sorted(path for path in lane_root.iterdir() if path.is_dir() and not path.name.startswith(".")):
            actual = {path.name for path in feature.glob("*.md")}
            assert actual == {"spec.md", "plan.md", "tasks.md", "verification.md"}, (
                f"{feature.relative_to(REPO_ROOT)} must contain the complete SDD artifact set"
            )


def test_sdd_root_has_templates_and_feature_lanes_only() -> None:
    children = sorted(p.name for p in SDD.iterdir() if not p.name.startswith("."))
    assert set(children) == {"README.md", "_templates", "features"}, children

    template_files = {p.name for p in (SDD / "_templates").glob("*.md")}
    assert template_files == {
        "README.md",
        "spec-template.md",
        "plan-template.md",
        "tasks-template.md",
        "verification-template.md",
    }

    feature_children = sorted(p.name for p in (SDD / "features").iterdir() if not p.name.startswith("."))
    assert set(feature_children) == {"active", "completed"}, feature_children


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


def test_make_check_all_runs_executable_sdd_harness() -> None:
    makefile = _read(REPO_ROOT / "Makefile")
    check_all = makefile.split("check-all:", 1)[1].split("\n\n", 1)[0]

    assert "scripts/validate_sdd_artifacts.py --check" in check_all
    assert "scripts/regen_sdd_work_index.py --check" in check_all


def test_make_check_all_checks_cli_help_snapshot() -> None:
    makefile = _read(REPO_ROOT / "Makefile")
    check_all = makefile.split("check-all:", 1)[1].split("\n\n", 1)[0]

    assert "scripts/regen_cli_help.py --check" in check_all


def test_generated_readme_source_map_points_to_existing_paths() -> None:
    readme = _read(DOCS / "generated" / "README.md")
    table_rows = [
        line
        for line in readme.splitlines()
        if line.startswith("| `") and "` |" in line and not line.startswith("| File ")
    ]

    assert table_rows, "docs/generated/README.md must document generated sources"
    for row in table_rows:
        cells = [cell.strip() for cell in row.strip("|").split("|")]
        assert len(cells) == 3, f"unexpected generated README row shape: {row}"

        generated_name = cells[0].strip("`")
        script_path = cells[2].strip("`")
        assert (DOCS / "generated" / generated_name).is_file(), f"generated file not found: {generated_name}"
        assert (REPO_ROOT / script_path).is_file(), f"generator script not found: {script_path}"

        for token in re.findall(r"`([^`]+)`", cells[1]):
            if "/" not in token and not token.endswith((".py", ".md", ".json", ".yaml", ".yml", ".toml")):
                continue
            source_path = REPO_ROOT / token.rstrip("/")
            assert source_path.exists(), f"generated README source path does not exist: {token}"


def test_architecture_doc_test_references_are_path_qualified_and_existing() -> None:
    architecture = _read(DOCS / "ARCHITECTURE.md")
    references = [
        token
        for token in re.findall(r"`([^`]+)`", architecture)
        if token.startswith("test_") or token.startswith("tests/architecture/")
    ]
    assert references, "docs/ARCHITECTURE.md must name architecture tests for enforced boundaries"

    for reference in references:
        assert reference.startswith("tests/architecture/"), (
            "docs/ARCHITECTURE.md test references must be path-qualified: "
            f"{reference}"
        )
        test_path_text, _, test_name = reference.partition("::")
        test_path = REPO_ROOT / test_path_text
        assert test_path.is_file(), f"docs/ARCHITECTURE.md references missing test file: {reference}"
        if test_name:
            test_source = _read(test_path)
            assert f"def {test_name}(" in test_source, (
                "docs/ARCHITECTURE.md references missing test function: "
                f"{reference}"
            )


def test_architecture_module_map_links_every_domain_architecture_doc() -> None:
    architecture = _read(DOCS / "ARCHITECTURE.md")
    expected = sorted(
        path.relative_to(REPO_ROOT).as_posix()
        for path in (REPO_ROOT / "src" / "parallax" / "domains").glob("*/ARCHITECTURE.md")
    )
    linked = sorted(
        link.lstrip("./")
        for link in re.findall(r"\[[^\]]+\]\((\.\./src/parallax/domains/[^)]+/ARCHITECTURE\.md)\)", architecture)
    )

    assert linked == expected


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
