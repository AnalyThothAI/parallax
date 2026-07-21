from __future__ import annotations

import ast
from pathlib import Path

from parallax.app.runtime.worker_manifest import all_worker_manifests

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "parallax"
FORBIDDEN_CURRENT_IDENTITY_PARTS = frozenset(
    {
        "attempt_id",
        "computed_at_ms",
        "generation",
        "generation_id",
        "published_at_ms",
        "run_id",
        "snapshot_id",
    }
)


def _python_files(root: Path) -> list[Path]:
    return sorted(
        path
        for path in root.rglob("*.py")
        if "alembic/versions" not in path.as_posix() and "__pycache__" not in path.parts
    )


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _imports(path: Path) -> set[str]:
    imports: set[str] = set()
    for node in ast.walk(_tree(path)):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def _relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _forbidden_imports(root: Path, prefixes: tuple[str, ...]) -> dict[str, list[str]]:
    violations = {
        _relative(path): sorted(name for name in _imports(path) if name.startswith(prefixes))
        for path in _python_files(root)
    }
    return {path: names for path, names in violations.items() if names}


def _argument_names(function: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    arguments = function.args
    return {
        argument.arg
        for argument in (
            *arguments.posonlyargs,
            *arguments.args,
            *arguments.kwonlyargs,
        )
    }


def _attribute_calls(tree: ast.AST, attribute: str) -> list[int]:
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == attribute
    ]


def test_dependency_graph_is_one_way() -> None:
    assert (
        _forbidden_imports(
            SRC / "platform",
            ("parallax.app", "parallax.domains", "parallax.integrations"),
        )
        == {}
    )
    assert (
        _forbidden_imports(
            SRC / "domains",
            ("parallax.app", "parallax.integrations"),
        )
        == {}
    )
    assert (
        _forbidden_imports(
            SRC / "app" / "runtime",
            ("parallax.app.surfaces",),
        )
        == {}
    )


def test_public_read_paths_do_not_import_provider_implementations() -> None:
    roots = [SRC / "app" / "surfaces" / "api"]
    roots.extend(path for path in (SRC / "domains").glob("*/queries") if path.is_dir())
    roots.extend(path for path in (SRC / "domains").glob("*/read_models") if path.is_dir())
    violations: dict[str, list[str]] = {}
    for root in roots:
        violations.update(
            _forbidden_imports(
                root,
                ("parallax.integrations", "parallax.app.runtime.provider_wiring"),
            )
        )
    assert violations == {}


def test_repository_public_api_has_one_transaction_owner() -> None:
    violations: dict[str, object] = {}
    repository_files = sorted((SRC / "domains").glob("*/repositories/*.py"))
    for path in repository_files:
        tree = _tree(path)
        commit_arguments: list[str] = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) or node.name.startswith("_"):
                continue
            forbidden = _argument_names(node) & {"commit", "auto_commit"}
            commit_arguments.extend(f"{node.name}:{name}" for name in sorted(forbidden))
        transaction_calls = _attribute_calls(tree, "transaction")
        commit_calls = _attribute_calls(tree, "commit")
        if commit_arguments or transaction_calls or commit_calls:
            violations[_relative(path)] = {
                "commit_arguments": commit_arguments,
                "transaction_calls": transaction_calls,
                "commit_calls": commit_calls,
            }
    assert violations == {}


def test_domain_workers_use_platform_runtime_kernel() -> None:
    violations = _forbidden_imports(
        SRC / "domains",
        ("parallax.app.runtime.worker_base", "parallax.app.runtime.worker_result"),
    )
    assert violations == {}


def test_worker_manifest_has_unique_names_and_one_writer_per_read_model() -> None:
    manifests = all_worker_manifests()
    names = [manifest.name for manifest in manifests]
    declared_tables = [table for manifest in manifests for table, _identity in manifest.current_read_model_identities]

    assert len(names) == len(set(names))
    assert len(declared_tables) == len(set(declared_tables))


def test_current_read_model_identities_are_stable_product_keys() -> None:
    violations = {
        f"{manifest.name}:{table}": sorted(set(identity) & FORBIDDEN_CURRENT_IDENTITY_PARTS)
        for manifest in all_worker_manifests()
        for table, identity in manifest.current_read_model_identities
        if set(identity) & FORBIDDEN_CURRENT_IDENTITY_PARTS
    }
    assert violations == {}


def test_worker_manifest_is_static_data() -> None:
    tree = _tree(SRC / "app" / "runtime" / "worker_manifest.py")
    imported_modules = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    dynamic_calls = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "__import__"
    ]

    assert not any(module == "importlib" or module.startswith("importlib.") for module in imported_modules)
    assert dynamic_calls == []


def test_hot_status_path_does_not_sample_queues() -> None:
    path = SRC / "app" / "surfaces" / "api" / "app.py"
    tree = _tree(path)
    forbidden_imports = [name for name in _imports(path) if name.endswith("queue_health") or ".queue_health." in name]
    forbidden_attributes = [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Attribute) and node.attr in {"queue_depth", "_queue_health_cache"}
    ]

    assert forbidden_imports == []
    assert forbidden_attributes == []
