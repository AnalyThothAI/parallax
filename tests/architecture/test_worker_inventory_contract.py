from __future__ import annotations

import ast
import inspect
import re
import textwrap
from pathlib import Path

import pytest

from gmgn_twitter_intel.app.runtime.wake_bus import WakeBus
from tests.architecture.test_worker_runtime_contracts import EXPECTED_WORKERS, SINGLE_WRITER_READ_MODELS

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src" / "gmgn_twitter_intel"
DOCS_WORKERS = ROOT / "docs" / "WORKERS.md"
REPOSITORY_SESSION = SRC / "app" / "runtime" / "repository_session.py"
WRITE_METHOD_PREFIXES = (
    "clear",
    "delete",
    "demote",
    "enqueue",
    "finish",
    "insert",
    "mark",
    "record",
    "replace",
    "set",
    "upsert",
    "update",
)


@pytest.mark.architecture
def test_worker_inventory_keys_match_runtime_registry_and_settings() -> None:
    from gmgn_twitter_intel.app.runtime.worker_registry import CANONICAL_WORKER_CLASSES, CANONICAL_WORKER_NAMES
    from gmgn_twitter_intel.platform.config.settings import WorkersSettings

    inventory = _worker_inventory()
    marker_keys = _worker_inventory_marker_keys()
    table_keys = set(inventory)
    registry_keys = set(CANONICAL_WORKER_NAMES)
    class_keys = set(CANONICAL_WORKER_CLASSES)
    settings_keys = set(WorkersSettings.model_fields) - {"defaults", "agent_runtime"}

    assert marker_keys == registry_keys, _key_diff_message("worker-inventory marker", marker_keys, registry_keys)
    assert table_keys == registry_keys, _key_diff_message("Worker Inventory table", table_keys, registry_keys)
    assert class_keys == registry_keys, _key_diff_message("CANONICAL_WORKER_CLASSES", class_keys, registry_keys)
    assert settings_keys == registry_keys, _key_diff_message("WorkersSettings", settings_keys, registry_keys)


@pytest.mark.architecture
def test_documented_wake_inputs_match_default_worker_settings() -> None:
    from gmgn_twitter_intel.platform.config.settings import WorkersSettings

    inventory = _worker_inventory()
    settings = WorkersSettings()
    mismatches: list[str] = []
    for worker_key in sorted(set(WorkersSettings.model_fields) - {"defaults", "agent_runtime"}):
        expected = set(getattr(getattr(settings, worker_key), "wakes_on", ()))
        documented = _cell_code_values(inventory[worker_key]["Wake-in"])
        missing = sorted(expected - documented)
        extra = sorted(documented - expected)
        if missing or extra:
            mismatches.append(
                f"{worker_key} Wake-in mismatch: missing={missing}, extra={extra}, "
                f"expected={sorted(expected)}, documented={sorted(documented)}"
            )

    assert mismatches == []


@pytest.mark.architecture
def test_wake_bus_notify_channels_are_documented_as_wake_outputs() -> None:
    inventory = _worker_inventory()
    documented_wake_out = {channel for row in inventory.values() for channel in _cell_code_values(row["Wake-out"])}
    notify_channels = _wake_bus_notify_channels()

    missing = sorted(notify_channels - documented_wake_out)
    assert missing == [], (
        "WakeBus notify channels missing from at least one Worker Inventory Wake-out cell: "
        f"{missing}; documented={sorted(documented_wake_out)}"
    )


@pytest.mark.architecture
def test_documented_single_writer_read_models_match_runtime_allowlist() -> None:
    inventory = _worker_inventory()
    expected_by_table, derivation_problems = _derived_read_model_writer_rows()
    documented_by_table: dict[str, list[str]] = {table: [] for table in SINGLE_WRITER_READ_MODELS}
    for worker_key, row in inventory.items():
        writes = _cell_code_values(row["Writes"])
        for table, documented_workers in documented_by_table.items():
            if table in writes:
                documented_workers.append(worker_key)

    problems: list[str] = list(derivation_problems)
    for table, documented_workers in sorted(documented_by_table.items()):
        expected_workers = expected_by_table.get(table, [])
        if documented_workers != expected_workers:
            problems.append(
                f"{table} should appear in exactly the derived writer Writes cells; "
                f"expected={expected_workers}, documented={documented_workers}"
            )

    assert problems == []


def _derived_read_model_writer_rows() -> tuple[dict[str, list[str]], list[str]]:
    worker_paths = {key: _qualified_worker_module_path(qualified) for key, qualified in EXPECTED_WORKERS.items()}
    repository_attrs = _repository_attrs_by_path()
    dependency_paths = {key: _local_dependency_closure(path) for key, path in worker_paths.items()}
    attribute_calls = {key: _repository_write_calls(paths) for key, paths in dependency_paths.items()}

    expected_by_table: dict[str, list[str]] = {}
    problems: list[str] = []
    for table, allowlist in SINGLE_WRITER_READ_MODELS.items():
        owners = {
            worker_key
            for worker_key, worker_path in worker_paths.items()
            if any(_is_runtime_owner_path(worker_path, path) for path in allowlist)
        }
        if not owners:
            allowed_repository_attrs = {attr for path in allowlist for attr in repository_attrs.get(path, set())}
            owners = {
                worker_key
                for worker_key, calls in attribute_calls.items()
                if any(attr in calls for attr in allowed_repository_attrs)
            }

        expected_by_table[table] = sorted(owners)
        if not owners:
            allowed = ", ".join(sorted(_rel(path) for path in allowlist))
            problems.append(
                f"{table} has no runtime worker owner derivable from SINGLE_WRITER_READ_MODELS. "
                f"Add the writer runtime module to the table allowlist or ensure the worker makes a mutating "
                f"RepositorySession call through one of its allowlisted repositories: {allowed}"
            )
        elif len(owners) != 1:
            problems.append(
                f"{table} has {len(owners)} derived runtime writer owners from SINGLE_WRITER_READ_MODELS: "
                f"{sorted(owners)}"
            )
    return expected_by_table, problems


def _qualified_worker_module_path(qualified_name: str) -> Path:
    module_name = qualified_name.rpartition(".")[0]
    relative = Path(*module_name.split(".")).relative_to("gmgn_twitter_intel").with_suffix(".py")
    return SRC / relative


def _is_runtime_owner_path(worker_path: Path, allowlist_path: Path) -> bool:
    if _is_repository_path(allowlist_path) or _is_alembic_path(allowlist_path):
        return False
    return allowlist_path == worker_path


def _repository_attrs_by_path() -> dict[Path, set[str]]:
    class_paths = _class_paths()
    attrs_by_path: dict[Path, set[str]] = {}
    tree = _parse(REPOSITORY_SESSION)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name) or node.func.id != "RepositorySession":
            continue
        for keyword in node.keywords:
            if keyword.arg is None or not isinstance(keyword.value, ast.Call):
                continue
            repository_class = keyword.value.func
            if not isinstance(repository_class, ast.Name):
                continue
            path = class_paths.get(repository_class.id)
            if path is not None:
                attrs_by_path.setdefault(path, set()).add(keyword.arg)
    return attrs_by_path


def _class_paths() -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for path in SRC.rglob("*.py"):
        if _is_alembic_path(path):
            continue
        tree = _parse(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                paths.setdefault(node.name, path)
    return paths


def _local_dependency_closure(entry_path: Path) -> set[Path]:
    seen: set[Path] = set()
    pending = [entry_path]
    while pending:
        path = pending.pop()
        if path in seen or not path.exists() or _is_alembic_path(path):
            continue
        seen.add(path)
        pending.extend(imported for imported in _local_import_paths(path) if imported not in seen)
    return seen


def _local_import_paths(path: Path) -> set[Path]:
    paths: set[Path] = set()
    for node in ast.walk(_parse(path)):
        module_names: list[str] = []
        if isinstance(node, ast.Import):
            module_names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            module_names.append(node.module)
        for module_name in module_names:
            imported = _module_path(module_name)
            if imported is not None:
                paths.add(imported)
    return paths


def _module_path(module_name: str) -> Path | None:
    prefix = "gmgn_twitter_intel."
    if not module_name.startswith(prefix):
        return None
    relative = Path(*module_name[len(prefix) :].split("."))
    module_path = (SRC / relative).with_suffix(".py")
    if module_path.exists():
        return module_path
    package_path = SRC / relative / "__init__.py"
    if package_path.exists():
        return package_path
    return None


def _repository_write_calls(paths: set[Path]) -> set[str]:
    attrs: set[str] = set()
    for path in paths:
        for node in ast.walk(_parse(path)):
            if not isinstance(node, ast.Call):
                continue
            call = node.func
            if not isinstance(call, ast.Attribute) or not _is_write_method(call.attr):
                continue
            receiver = call.value
            if isinstance(receiver, ast.Attribute):
                attrs.add(receiver.attr)
    return attrs


def _is_write_method(method_name: str) -> bool:
    return method_name.startswith(WRITE_METHOD_PREFIXES)


def _rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def _is_repository_path(path: Path) -> bool:
    return "repositories" in path.parts


def _is_alembic_path(path: Path) -> bool:
    return "alembic" in path.parts


def _parse(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _worker_inventory() -> dict[str, dict[str, str]]:
    section = _section_text(DOCS_WORKERS.read_text(encoding="utf-8"), "Worker Inventory")
    rows = [line for line in section.splitlines() if line.startswith("|")]
    assert len(rows) >= 3, "docs/WORKERS.md Worker Inventory table is missing or malformed"
    headers = _split_markdown_row(rows[0])
    assert "Worker" in headers, f"Worker Inventory table headers missing Worker column: {headers}"
    inventory: dict[str, dict[str, str]] = {}
    for row in rows[2:]:
        cells = _split_markdown_row(row)
        assert len(cells) == len(headers), f"Malformed Worker Inventory row: {row}"
        item = dict(zip(headers, cells, strict=True))
        worker_key = _worker_key_from_cell(item["Worker"])
        assert worker_key not in inventory, f"Duplicate worker inventory row for {worker_key}"
        inventory[worker_key] = item
    return inventory


def _worker_inventory_marker_keys() -> set[str]:
    text = DOCS_WORKERS.read_text(encoding="utf-8")
    marker = re.search(r"<!--\s*worker-inventory-keys:\s*(.*?)\s*-->", text, re.DOTALL)
    assert marker is not None, "docs/WORKERS.md is missing <!-- worker-inventory-keys: ... --> marker"
    return {key.strip() for key in marker.group(1).replace("\n", " ").split(",") if key.strip()}


def _wake_bus_notify_channels() -> set[str]:
    channels: set[str] = set()
    for name, method in inspect.getmembers(WakeBus, predicate=inspect.isfunction):
        if not name.startswith("notify_"):
            continue
        tree = ast.parse(textwrap.dedent(inspect.getsource(method)))
        literals = [
            node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)
        ]
        assert literals, f"WakeBus.{name} does not expose a literal channel name"
        channels.add(literals[0])
    return channels


def _section_text(text: str, heading: str) -> str:
    pattern = rf"^## {re.escape(heading)}\s*$"
    match = re.search(pattern, text, re.MULTILINE)
    assert match is not None, f"docs/WORKERS.md missing ## {heading} section"
    next_heading = re.search(r"^## ", text[match.end() :], re.MULTILINE)
    end = match.end() + next_heading.start() if next_heading else len(text)
    return text[match.end() : end]


def _split_markdown_row(row: str) -> list[str]:
    return [cell.strip() for cell in row.strip().strip("|").split("|")]


def _worker_key_from_cell(cell: str) -> str:
    match = re.match(r"`([^`]+)`", cell)
    assert match is not None, f"Worker cell must start with canonical key in backticks: {cell}"
    return match.group(1)


def _cell_code_values(cell: str) -> set[str]:
    return set(re.findall(r"`([^`]+)`", cell))


def _key_diff_message(label: str, actual: set[str], expected: set[str]) -> str:
    return (
        f"{label} worker keys differ from canonical registry: "
        f"missing={sorted(expected - actual)}, extra={sorted(actual - expected)}"
    )
