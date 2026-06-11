"""Structural assertions for the docs harness."""

from __future__ import annotations

import ast
import os
import re
from pathlib import Path

from scripts.validate_sdd_artifacts import MAX_ACTIVE_FEATURE_TASKS

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
TECH_DEBT_ROOTED_PREFIXES = ("src/", "tests/", "web/", "scripts/", "docs/")
TECH_DEBT_PARALLAX_PREFIXES = (
    "app/",
    "domains/",
    "integrations/",
    "platform/",
    "runtime/",
    "services/",
    "types/",
)
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

GOVERNANCE_RULE_ANCHORS = {
    "asgi worker ownership": {
        "owner": "RELIABILITY.md",
        "anchors": ("ASGI worker", "Multiple workers", "collector"),
    },
    "token radar versioning": {
        "owner": "CONTRACTS.md",
        "anchors": ("projection_version", "factor_version", "Token Radar"),
    },
    "integration test storage boundary": {
        "owner": "TESTING.md",
        "anchors": ("Integration tests", "real PostgreSQL", "tests/integration/"),
    },
    "agent worktree policy": {
        "owner": "WORKFLOW.md",
        "anchors": ("git worktree add", ".worktrees/<slug>", "branch from `main`"),
    },
    "design audit before creation": {
        "owner": "DESIGN_DISCIPLINE.md",
        "anchors": ("existing `*_service.py`", "Trace the data flow", "fields already in the DB"),
    },
    "single config source": {
        "owner": "SECURITY.md",
        "anchors": ("~/.parallax/config.yaml", "~/.parallax/workers.yaml", "Do not introduce a third config path"),
    },
}


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def _governance_paths() -> dict[str, Path]:
    return {name: DOCS / name for name in EXPECTED_GOVERNANCE}


def _has_rule_anchors(text: str, anchors: tuple[str, ...]) -> bool:
    return all(anchor in text for anchor in anchors)


def _tech_debt_open_section() -> str:
    tech_debt = _read(DOCS / "TECH_DEBT.md")
    return tech_debt.split("## Open", 1)[1].split("## Closed", 1)[0]


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


def _tech_debt_path_candidate(reference: str) -> tuple[Path, str]:
    path_text = reference.split("::", 1)[0]
    path_text = re.sub(r":\d+(?:-\d+)?$", "", path_text)

    if path_text.startswith(TECH_DEBT_ROOTED_PREFIXES):
        return REPO_ROOT / path_text, path_text

    raise ValueError(f"not a source path reference: {reference}")


def _tech_debt_referenced_test_name(reference: str) -> str:
    parts = reference.split("::")
    if len(parts) < 2:
        return ""
    return parts[-1]


def _tech_debt_table_rows() -> list[list[str]]:
    rows: list[list[str]] = []
    for line in _tech_debt_open_section().splitlines():
        if not line.startswith("|") or line.startswith("|---") or line.startswith("| Description"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) == 6:
            rows.append(cells)
    return rows


def _is_type_get_call(node: ast.AST) -> bool:
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get"
        and bool(node.args)
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == "type"
    )


def _websocket_type_literals() -> set[str]:
    tree = ast.parse(_read(REPO_ROOT / "src/parallax/app/surfaces/api/ws.py"))
    literals: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values, strict=True):
                if (
                    isinstance(key, ast.Constant)
                    and key.value == "type"
                    and isinstance(value, ast.Constant)
                    and isinstance(value.value, str)
                ):
                    literals.add(value.value)
        if isinstance(node, ast.Compare) and _is_type_get_call(node.left):
            literals.update(
                comparator.value
                for comparator in node.comparators
                if isinstance(comparator, ast.Constant) and isinstance(comparator.value, str)
            )
    return literals


def _looks_like_unrooted_source_reference(reference: str) -> bool:
    if reference.startswith((*TECH_DEBT_ROOTED_PREFIXES, "~", "/")):
        return False
    if " " in reference or "=" in reference:
        return False
    if reference.startswith(TECH_DEBT_PARALLAX_PREFIXES):
        return True
    return reference.endswith((".py", ".ts", ".tsx", ".md", ".yaml", ".yml", ".toml"))


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


def test_sdd_docs_describe_bounded_active_feature_records() -> None:
    documents = (
        DOCS / "WORKFLOW.md",
        SDD / "README.md",
        SDD / "_templates" / "tasks-template.md",
    )
    required_tokens = (
        f"{MAX_ACTIVE_FEATURE_TASKS} structured tasks",
        "active-feature-too-large",
        "split or supersede",
    )

    for document in documents:
        text = _read(document)
        for token in required_tokens:
            assert token in text, f"{document.relative_to(REPO_ROOT)} does not mention {token!r}"


def test_sdd_verification_template_avoids_stale_spec_section_anchors() -> None:
    template = _read(SDD / "_templates" / "verification-template.md")

    assert "§6.4" not in template
    assert "current feature spec" in template
    assert "make check-sdd-completion FEATURE=<slug>" in template


def test_sdd_verification_template_uses_machine_readable_status_examples() -> None:
    template = _read(SDD / "_templates" / "verification-template.md")

    assert "✅" not in template
    assert "❌" not in template
    assert "≥" not in template
    assert "| AC1 - WHEN ... THEN system SHALL ... | Pass |" in template
    assert "| line | 91% | >= 80% | Pass |" in template
    assert "| branch | Not run | >= 70% | Fail |" in template


def test_docs_root_governance_files() -> None:
    actual = {p.name for p in DOCS.glob("*.md")}
    assert actual == EXPECTED_GOVERNANCE, f"unexpected docs root contents: {actual ^ EXPECTED_GOVERNANCE}"


def test_no_legacy_files_at_docs_root() -> None:
    legacy = sorted(p.name for p in DOCS.glob("2026-*-cn.md"))
    legacy += sorted(p.name for p in DOCS.glob("token-radar-social-heat-*.md"))
    assert legacy == [], f"legacy files still at docs root: {legacy}"


def test_repo_root_has_no_loose_visual_artifacts() -> None:
    visual_suffixes = {".gif", ".jpeg", ".jpg", ".png", ".webp"}
    loose_visuals = sorted(
        path.name
        for path in REPO_ROOT.iterdir()
        if path.is_file() and path.suffix.lower() in visual_suffixes
    )

    assert loose_visuals == [], (
        "visual verification artifacts must live under an owned artifact directory, "
        f"not repo root: {loose_visuals}"
    )


def test_rule_ownership() -> None:
    governance_paths = _governance_paths()
    for rule_name, contract in GOVERNANCE_RULE_ANCHORS.items():
        owner = contract["owner"]
        anchors = contract["anchors"]
        # Missing docs should fail loudly here instead of being hidden by a
        # path.exists() guard; docs-root inventory has its own focused failure.
        hits = [
            name
            for name, path in governance_paths.items()
            if _has_rule_anchors(_read(path), anchors)
        ]
        assert hits == [owner], f"rule {rule_name!r} expected only in {owner}, found in {hits}"


def test_routers_have_no_governance_phrases() -> None:
    for rule_name, contract in GOVERNANCE_RULE_ANCHORS.items():
        anchors = contract["anchors"]
        leaked = [
            router
            for router in ROUTER_FILES
            if _has_rule_anchors(_read(REPO_ROOT / router), anchors)
        ]
        assert leaked == [], f"rule {rule_name!r} leaked into router files: {leaked}"


def test_make_check_all_runs_executable_sdd_harness() -> None:
    makefile = _read(REPO_ROOT / "Makefile")
    check_all = makefile.split("check-all:", 1)[1].split("\n\n", 1)[0]

    assert "scripts/validate_sdd_artifacts.py" in check_all
    assert "scripts/validate_sdd_artifacts.py --check" not in check_all
    assert "scripts/check_sdd_gate.py --all-active" in check_all
    assert "scripts/check_sdd_gate.py --all-active --check" not in check_all
    assert "scripts/regen_sdd_work_index.py --check" in check_all


def test_makefile_pytest_targets_do_not_accept_empty_collections() -> None:
    makefile = _read(REPO_ROOT / "Makefile")
    assert "[ $$ec -eq 5 ] && exit 0" not in makefile
    assert "; ec=$$?" not in makefile


def test_contract_lane_has_no_duplicate_make_alias() -> None:
    makefile = _read(REPO_ROOT / "Makefile")
    phony_targets = makefile.split(".PHONY:", 1)[1].split("\n", 1)[0].split()

    assert "test-contract" in phony_targets
    assert "contract-check" not in phony_targets
    assert "\ncontract-check:" not in makefile


def test_golden_lane_uses_dedicated_pytest_marker() -> None:
    makefile = _read(REPO_ROOT / "Makefile")
    root_conftest = _read(REPO_ROOT / "tests" / "conftest.py")
    golden_conftest = _read(REPO_ROOT / "tests" / "golden" / "conftest.py")
    golden_target = makefile.split("test-golden:", 1)[1].split("\n\n", 1)[0]

    assert '"golden"' in root_conftest
    assert "-m golden" in golden_target
    assert "-m e2e" not in golden_target
    assert "pytest.mark.golden" in golden_conftest
    assert "pytest.mark.e2e" not in golden_conftest


def test_final_runtime_lanes_do_not_expose_skip_env_switches() -> None:
    checked_paths = (
        REPO_ROOT / "tests" / "e2e" / "conftest.py",
        REPO_ROOT / "tests" / "golden" / "conftest.py",
        DOCS / "sdd" / "_templates" / "verification-template.md",
    )
    for path in checked_paths:
        text = _read(path)
        assert "SKIP_E2E" not in text
        assert "SKIP_GOLDEN" not in text
        assert "cannot serve as verification evidence" not in text


def test_makefile_exposes_single_feature_sdd_completion_gate() -> None:
    makefile = _read(REPO_ROOT / "Makefile")
    workflow = _read(DOCS / "WORKFLOW.md")
    sdd_readme = _read(DOCS / "sdd" / "README.md")
    assert "check-sdd-completion:" in makefile
    completion_target = makefile.split("check-sdd-completion:", 1)[1].split("\n\n", 1)[0]

    assert "check-sdd-completion" in makefile.split(".PHONY:", 1)[1].split("\n", 1)[0]
    assert 'test -n "$(FEATURE)"' in completion_target
    assert "$(MAKE) check-all" in completion_target
    assert 'scripts/check_sdd_gate.py --feature "$(FEATURE)" --gate verify' in completion_target
    assert 'scripts/check_sdd_gate.py --feature "$(FEATURE)" --gate verify --check' not in completion_target
    assert completion_target.index("$(MAKE) check-all") < completion_target.index("scripts/check_sdd_gate.py")
    assert "make check-sdd-completion FEATURE=<slug>" in workflow
    assert "make check-sdd-completion FEATURE=<slug>" in sdd_readme


def test_make_check_all_checks_cli_help_snapshot() -> None:
    makefile = _read(REPO_ROOT / "Makefile")
    check_all = makefile.split("check-all:", 1)[1].split("\n\n", 1)[0]

    assert "scripts/regen_cli_help.py --check" in check_all


def test_make_check_all_checks_ws_protocol_snapshot() -> None:
    makefile = _read(REPO_ROOT / "Makefile")
    check_all = makefile.split("check-all:", 1)[1].split("\n\n", 1)[0]

    assert "scripts/regen_ws_protocol.py --check" in check_all


def test_make_check_all_checks_score_versions_snapshot() -> None:
    makefile = _read(REPO_ROOT / "Makefile")
    check_all = makefile.split("check-all:", 1)[1].split("\n\n", 1)[0]

    assert "scripts/regen_score_versions.py --check" in check_all


def test_make_check_all_checks_non_db_generated_snapshots() -> None:
    makefile = _read(REPO_ROOT / "Makefile")
    check_all = makefile.split("check-all:", 1)[1].split("\n\n", 1)[0]
    readme = _read(DOCS / "generated" / "README.md")
    script_paths = [
        cells[2].strip("`")
        for line in readme.splitlines()
        if line.startswith("| `") and "` |" in line and not line.startswith("| File ")
        for cells in ([cell.strip() for cell in line.strip("|").split("|")],)
    ]

    assert script_paths, "docs/generated/README.md must document generated sources"
    for script_path in script_paths:
        if script_path == "scripts/regen_db_schema.py":
            continue
        assert f"{script_path} --check" in check_all


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


def test_generated_ws_protocol_documents_current_type_literals() -> None:
    expected = _websocket_type_literals()
    protocol = _read(DOCS / "generated" / "ws-protocol.md")
    missing = sorted(type_literal for type_literal in expected if f"`{type_literal}`" not in protocol)

    assert expected, "src/parallax/app/surfaces/api/ws.py must expose WebSocket type literals"
    assert "Message type literal" in protocol
    assert missing == [], f"docs/generated/ws-protocol.md omits WebSocket type literals: {missing}"


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


def test_open_tech_debt_references_current_source_and_test_paths() -> None:
    open_debt = _tech_debt_open_section()
    backticked_references = re.findall(r"`([^`]+)`", open_debt)
    references = [
        token
        for token in backticked_references
        if token.startswith(TECH_DEBT_ROOTED_PREFIXES)
    ]
    bare_test_references = [token for token in backticked_references if token.startswith("::test")]
    unrooted_source_references = [
        token for token in backticked_references if _looks_like_unrooted_source_reference(token)
    ]

    assert references, "docs/TECH_DEBT.md open debt must keep source-backed references"
    assert bare_test_references == [], (
        "open TECH_DEBT test references must include their source file: "
        f"{bare_test_references}"
    )
    assert unrooted_source_references == [], (
        "open TECH_DEBT source/test/doc references must be repo-root paths: "
        f"{unrooted_source_references}"
    )

    missing_paths: list[str] = []
    missing_tests: list[str] = []
    for reference in references:
        path, path_text = _tech_debt_path_candidate(reference)
        if not path.exists():
            missing_paths.append(reference)
            continue

        test_name = _tech_debt_referenced_test_name(reference)
        if test_name and path.suffix == ".py":
            source = _read(path)
            if not re.search(rf"^\s*def\s+{re.escape(test_name)}\(", source, re.MULTILINE):
                missing_tests.append(reference)

        assert path_text != "tests/test_harness_structure.py", "use the executable architecture harness path"

    assert missing_paths == [], f"open TECH_DEBT references missing files: {missing_paths}"
    assert missing_tests == [], f"open TECH_DEBT references missing test functions: {missing_tests}"


def test_open_tech_debt_duplicate_symbol_claims_match_current_sources() -> None:
    stale_claims: list[str] = []
    for cells in _tech_debt_table_rows():
        description = cells[0]
        if "duplicated in" not in description:
            continue
        symbol_match = re.match(r"`([^`]+)` is duplicated in ", description)
        if symbol_match is None:
            continue
        symbol = symbol_match.group(1)
        source_references = [
            token
            for token in re.findall(r"`([^`]+)`", description)
            if token.startswith("src/") and token.endswith(".py")
        ]
        for reference in source_references:
            path = REPO_ROOT / reference
            if path.exists() and symbol not in _read(path):
                stale_claims.append(f"{symbol} is absent from {reference}")

    assert stale_claims == [], f"open TECH_DEBT duplicate-symbol claims are stale: {stale_claims}"


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
