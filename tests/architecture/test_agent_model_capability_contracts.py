from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "gmgn_twitter_intel"
PYPROJECT = ROOT / "pyproject.toml"
DOMAINS = SRC / "domains"
PROVIDER_WIRING_ROOTS = (
    SRC / "app" / "runtime",
    SRC / "app" / "surfaces",
    SRC / "integrations",
)
CAPABILITY_OWNER_ALLOWLIST = {
    SRC / "platform" / "agent_capabilities.py",
    SRC / "platform" / "config" / "settings.py",
}
STRUCTURED_OUTPUT_STRATEGY = SRC / "integrations" / "openai_agents" / "structured_output_strategy.py"

pytestmark = pytest.mark.architecture


def test_domains_and_provider_wiring_do_not_own_concrete_model_or_provider_tokens() -> None:
    forbidden_tokens = ("qwen", "deepseek", "litellm")
    violations: list[str] = []

    for path in _production_python_files(DOMAINS, *PROVIDER_WIRING_ROOTS):
        if path in CAPABILITY_OWNER_ALLOWLIST:
            continue
        for line_number, value in _non_docstring_string_constants(path):
            lowered = value.lower()
            violations.extend(
                f"{path.relative_to(ROOT)}:{line_number} contains {token!r}"
                for token in forbidden_tokens
                if token in lowered
            )

    assert violations == []


def test_response_format_is_owned_by_structured_output_strategy() -> None:
    violations: list[str] = []

    for path in _production_python_files(SRC):
        if path in {STRUCTURED_OUTPUT_STRATEGY, SRC / "platform" / "agent_capabilities.py"}:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.keyword) and node.arg == "response_format":
                violations.append(f"{path.relative_to(ROOT)}:{node.lineno} keyword response_format")
            if isinstance(node, ast.Name) and node.id == "response_format":
                violations.append(f"{path.relative_to(ROOT)}:{node.lineno} name response_format")
            if isinstance(node, ast.Constant) and node.value == "response_format":
                violations.append(f"{path.relative_to(ROOT)}:{node.lineno} string response_format")

    assert violations == []


def test_litellm_is_not_introduced_in_src_or_project_metadata() -> None:
    violations: list[str] = []

    for path in _production_python_files(SRC):
        text = path.read_text(encoding="utf-8").lower()
        if "litellm" in text:
            violations.append(path.relative_to(ROOT).as_posix())

    if "litellm" in PYPROJECT.read_text(encoding="utf-8").lower():
        violations.append(PYPROJECT.relative_to(ROOT).as_posix())

    assert violations == []


def test_agent_runtime_has_single_json_object_output_path() -> None:
    forbidden_tokens = (
        '"json_schema"',
        "'json_schema'",
        'schema_enforcement: str = "provider"',
        "schema_enforcement=provider",
        "AgentOutputStrategy.JSON_SCHEMA",
        "AgentSchemaEnforcement.PROVIDER",
        "AgentsJsonSchemaStrategy",
    )
    allowlist = {
        SRC / "integrations" / "openai_agents" / "agent_output_schema.py",
    }
    violations: list[str] = []

    for path in _production_python_files(SRC):
        if path in allowlist:
            continue
        text = path.read_text(encoding="utf-8")
        violations.extend(f"{path.relative_to(ROOT)} contains {token!r}" for token in forbidden_tokens if token in text)

    assert violations == []


def _production_python_files(*roots: Path) -> list[Path]:
    return sorted(
        path
        for root in roots
        for path in root.rglob("*.py")
        if "__pycache__" not in path.parts and "alembic" not in path.parts and path.is_file()
    )


def _non_docstring_string_constants(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    docstring_lines = _docstring_lines(tree)
    constants: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.lineno in docstring_lines:
                continue
            constants.append((node.lineno, node.value))
    return constants


def _docstring_lines(tree: ast.AST) -> set[int]:
    lines: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if not node.body:
            continue
        first = node.body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
            lines.update(range(first.lineno, first.end_lineno + 1))
    return lines
