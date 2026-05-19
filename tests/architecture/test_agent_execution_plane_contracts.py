from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "gmgn_twitter_intel"
OPENAI_AGENTS = SRC / "integrations" / "openai_agents"
GATEWAY_FILES = {
    OPENAI_AGENTS / "agent_execution_gateway.py",
    OPENAI_AGENTS / "instructor_safety_net.py",
}

pytestmark = pytest.mark.architecture


def _py_files(root: Path) -> list[Path]:
    return sorted(path for path in root.rglob("*.py") if "__pycache__" not in path.parts)


def _parse(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _imported_modules(tree: ast.AST) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def _import_aliases(tree: ast.AST) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                local_name = alias.asname or alias.name.split(".", maxsplit=1)[0]
                aliases[local_name] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            for alias in node.names:
                if alias.name == "*":
                    continue
                local_name = alias.asname or alias.name
                aliases[local_name] = f"{node.module}.{alias.name}"
    return aliases


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return f"{_call_name(node.value)}.{node.attr}"
    return ""


def _call_leaf(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _resolved_call_name(node: ast.AST, aliases: dict[str, str]) -> str:
    name = _call_name(node)
    base, separator, rest = name.partition(".")
    if base not in aliases:
        return name
    return f"{aliases[base]}{separator}{rest}" if separator else aliases[base]


def test_openai_agents_sdk_execution_only_in_gateway() -> None:
    violations: list[str] = []
    for path in _py_files(OPENAI_AGENTS):
        if path in GATEWAY_FILES:
            continue
        tree = _parse(path)
        aliases = _import_aliases(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = _call_name(node.func)
                leaf = _call_leaf(node.func)
                resolved_name = _resolved_call_name(node.func, aliases)
                if (
                    leaf in {"Agent", "RunConfig"}
                    or resolved_name in {"agents.Agent", "agents.RunConfig", "agents.run.RunConfig"}
                    or resolved_name.endswith(".Runner.run")
                    or name.endswith(".run")
                ):
                    violations.append(f"{path.relative_to(ROOT)}:{node.lineno} calls {resolved_name}")

    assert violations == []


def test_async_openai_constructed_only_by_llm_gateway_or_safety_net() -> None:
    allowlist = {
        SRC / "app" / "runtime" / "llm_gateway.py",
        OPENAI_AGENTS / "instructor_safety_net.py",
    }
    violations: list[str] = []
    for path in _py_files(SRC):
        if path in allowlist:
            continue
        tree = _parse(path)
        aliases = _import_aliases(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            resolved_name = _resolved_call_name(node.func, aliases)
            if _call_leaf(node.func) == "AsyncOpenAI" or resolved_name == "openai.AsyncOpenAI":
                violations.append(f"{path.relative_to(ROOT)}:{node.lineno} constructs {resolved_name}")

    assert violations == []


def test_agent_execution_gateway_does_not_import_domain_repositories() -> None:
    gateway = OPENAI_AGENTS / "agent_execution_gateway.py"
    if not gateway.exists():
        raise AssertionError("agent_execution_gateway.py must exist")
    imports = _imported_modules(_parse(gateway))
    violations = sorted(module for module in imports if ".repositories" in module or module.endswith(".repositories"))
    assert violations == []


def test_domain_packages_do_not_import_openai_agents_sdk() -> None:
    domain_root = SRC / "domains"
    forbidden_prefixes = ("agents", "agents.", "openai")
    violations: list[str] = []
    for path in _py_files(domain_root):
        imports = _imported_modules(_parse(path))
        for module in sorted(imports):
            if module.startswith(forbidden_prefixes):
                violations.append(f"{path.relative_to(ROOT)} imports {module}")

    assert violations == []


def test_watchlist_prompt_not_owned_by_openai_integration() -> None:
    path = OPENAI_AGENTS / "watchlist_summary_agent_client.py"
    if not path.exists():
        raise AssertionError("watchlist_summary_agent_client.py must exist")
    text = path.read_text(encoding="utf-8")
    assert "You summarize a watched crypto Twitter account" not in text
    assert "WatchlistHandleSummaryPayload" not in text
